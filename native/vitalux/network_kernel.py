#!/usr/bin/python3 -I
"""Linux socket accounting and the optional isolated Vitalux network helper.

This standalone standard-library file can be installed root-owned. It never
imports application code or runs shell commands. BPF links and session blocks
are released by the kernel when its descriptors close, including after a crash.
"""
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import socket
import struct
import sys
import tempfile
import time

MAX_SOCKETS=16384
MAX_MESSAGE=8192
STATES={1:'ESTABLISHED',2:'SYN_SENT',3:'SYN_RECV',4:'FIN_WAIT1',5:'FIN_WAIT2',
        6:'TIME_WAIT',7:'CLOSED',8:'CLOSE_WAIT',9:'LAST_ACK',10:'LISTEN',11:'CLOSING'}


def application(pid,uid):
    """Validate ownership and PID identity on both sides of the proc reads."""
    root=Path('/proc')/str(int(pid))
    try:
        if root.stat().st_uid!=uid:return None
        fields=(root/'stat').read_text().rsplit(')',1)[1].split()
        first=fields[19];parent=int(fields[1])
        name=(root/'comm').read_text().strip()[:128]
        try:exe=os.readlink(root/'exe')
        except OSError:exe=''
        key=exe or f'@{pid}:{first}'
        worker=Path(exe).name in ('QtWebEngineProcess','chrome_crashpad_handler')
        # Different Python/Node scripts must not share one executable-wide rule.
        if Path(exe).name.startswith(('python','node','ruby','perl')):
            with (root/'cmdline').open('rb') as stream:argv=stream.read(8192).split(b'\0')
            identity=[];index=1
            while index<len(argv) and argv[index]:
                arg=argv[index]
                if arg in (b'-c',b'-m',b'-e'):
                    identity=argv[index:index+2]
                    worker=arg==b'-c' and len(identity)>1 and b'multiprocessing.spawn' in identity[1]
                    break
                if arg in (b'-X',b'-W'):index+=2;continue
                if arg==b'--':index+=1;continue
                if arg.startswith(b'-'):index+=1;continue
                script=os.fsdecode(arg)
                if not os.path.isabs(script):script=os.path.normpath(os.path.join(os.readlink(root/'cwd'),script))
                identity=[os.fsencode(script)];name=Path(script).stem[:128];break
            if identity:key+='|'+hashlib.sha256(b'\0'.join(identity)).hexdigest()[:20]
        second=(root/'stat').read_text().rsplit(')',1)[1].split()[19]
        if first!=second or root.stat().st_uid!=uid:return None
        return dict(pid=int(pid),start=int(first),name=name,exe=exe,key=key,parent=parent,worker=worker)
    except (OSError,ValueError,IndexError):
        return None


def applications(uid):
    result={}
    with os.scandir('/proc') as entries:
        for entry in entries:
            if not entry.name.isdecimal():continue
            try:
                if entry.stat().st_uid!=uid:continue
            except OSError:continue
            app=application(int(entry.name),uid)
            if app:result[app['pid']]=app
            if len(result)>=16384:break
    for _ in range(8):
        changed=False
        for app in result.values():
            parent=result.get(app['parent'])
            if app['worker'] and parent and app['key']!=parent['key']:
                app.update(key=parent['key'],name=parent['name']);changed=True
        if not changed:break
    return result


def parse_diag(payload,protocol):
    if len(payload)<72:return None
    family,state=payload[0],payload[1]
    if family not in (socket.AF_INET,socket.AF_INET6):return None
    port,remote_port=struct.unpack_from('!HH',payload,4)
    length=4 if family==socket.AF_INET else 16
    local=socket.inet_ntop(family,payload[8:8+length])
    remote=socket.inet_ntop(family,payload[24:24+length])
    cookie=struct.unpack_from('=Q',payload,44)[0]
    uid,inode=struct.unpack_from('=II',payload,64)
    row=dict(cookie=cookie,uid=uid,inode=inode,protocol=protocol,
             local=local,local_port=port,remote=remote,remote_port=remote_port,
             state=STATES.get(state,str(state)),rx=None,tx=None)
    offset=72
    while offset+4<=len(payload):
        size,kind=struct.unpack_from('=HH',payload,offset)
        if size<4 or offset+size>len(payload):break
        info=payload[offset+4:offset+size]
        if protocol=='TCP' and kind==2 and len(info)>=136 and state!=10:
            row['rx']=struct.unpack_from('=Q',info,128)[0]
            # Prefer bytes actually sent over acknowledged bytes when present.
            row['tx']=struct.unpack_from('=Q',info,200 if len(info)>=208 else 120)[0]
        offset+=(size+3)&~3
    return row


def inet_sockets(uid):
    """INET_DIAG exposes real TCP counters; UDP stays unknown without BPF."""
    rows=[]
    errors=[]
    for family in (socket.AF_INET,socket.AF_INET6):
        for number,name in ((socket.IPPROTO_TCP,'TCP'),(socket.IPPROTO_UDP,'UDP')):
            try:
                with socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,4) as channel:
                    channel.settimeout(.8)
                    channel.bind((0,0))
                    sequence=time.monotonic_ns()&0xffffffff
                    request=struct.pack('=BBBBI',family,number,2,0,0xffffffff)+bytes(48)
                    header=struct.pack('=IHHII',16+len(request),20,0x301,sequence,0)
                    channel.send(header+request)
                    done=False
                    while not done:
                        packet=channel.recv(1<<20)
                        offset=0
                        while offset+16<=len(packet):
                            size,kind,flags,seq,_pid=struct.unpack_from('=IHHII',packet,offset)
                            if size<16 or offset+size>len(packet):raise OSError('Malformed INET_DIAG response')
                            payload=packet[offset+16:offset+size]
                            offset+=(size+3)&~3
                            if seq!=sequence:continue
                            if kind==3:
                                if flags&0x10:raise OSError('INET_DIAG dump interrupted')
                                done=True
                                break
                            if kind==2:
                                error=struct.unpack_from('=i',payload)[0] if len(payload)>=4 else -errno.EIO
                                if error:raise OSError(-error,os.strerror(-error))
                                continue
                            row=parse_diag(payload,name)
                            if row and row['uid']==uid and row['inode']:
                                rows.append(row)
                            if len(rows)>=MAX_SOCKETS:return rows,errors+['socket_limit']
            except OSError as exc:
                errors.append(f'{name}/{family}: {exc}')
    if errors:
        # Some containers implement /proc but not socket diagnostics. Never
        # turn queue lengths or interface counters into invented app traffic.
        known={(row['protocol'],row['inode']) for row in rows}
        for row in proc_sockets(uid):
            if (row['protocol'],row['inode']) not in known:rows.append(row)
    return rows,errors


def proc_sockets(uid):
    rows=[]
    for filename,protocol,ipv6 in (('tcp','TCP',False),('tcp6','TCP',True),
                                   ('udp','UDP',False),('udp6','UDP',True)):
        try:
            lines=Path('/proc/net',filename).read_text().splitlines()[1:]
        except OSError:continue
        def address(text):
            host,port=text.split(':')
            raw=bytes.fromhex(host)
            raw=b''.join(raw[i:i+4][::-1] for i in range(0,len(raw),4))
            return socket.inet_ntop(socket.AF_INET6 if ipv6 else socket.AF_INET,raw),int(port,16)
        for line in lines[:MAX_SOCKETS]:
            fields=line.split()
            try:
                owner,inode=int(fields[7]),int(fields[9])
                if owner!=uid or not inode:continue
                local,port=address(fields[1]);remote,remote_port=address(fields[2])
                # Negative synthetic identities cannot collide with BPF cookies.
                rows.append(dict(cookie=-inode,uid=owner,inode=inode,protocol=protocol,
                    local=local,local_port=port,remote=remote,remote_port=remote_port,
                    state=STATES.get(int(fields[3],16),fields[3]),rx=None,tx=None))
            except (ValueError,IndexError,OSError):continue
    return rows


def socket_snapshot(uid=None):
    uid=os.getuid() if uid is None else uid
    rows,errors=inet_sockets(uid)
    wanted={row['inode'] for row in rows}
    owners={}
    apps=applications(uid)
    for pid,app in sorted(apps.items()):
        try:
            with os.scandir(f'/proc/{pid}/fd') as entries:
                for index,entry in enumerate(entries):
                    if index>=65536:break
                    try:target=os.readlink(entry.path)
                    except OSError:continue
                    if target.startswith('socket:[') and target.endswith(']'):
                        try:inode=int(target[8:-1])
                        except ValueError:continue
                        if inode in wanted:owners.setdefault(inode,app)
        except OSError:continue
    for row in rows:
        app=owners.get(row['inode'])
        if app:row.update(app)
        else:row.update(pid=None,start=None,name='',exe='',key='@unassigned')
    return dict(monotonic=time.monotonic(),backend='tcp',connections=rows,
                errors=errors,applications=apps)


class Instructions:
    """Small, deterministic eBPF assembler; no compiler/BCC dependency."""
    def __init__(self):
        self.code=[]
        self.labels={}
        self.jumps=[]

    def emit(self,op,dst=0,src=0,offset=0,imm=0):
        self.code.append([op,dst,src,offset,imm])

    def label(self,name):self.labels[name]=len(self.code)

    def jump(self,op,dst,imm,label):
        self.jumps.append((len(self.code),label))
        self.emit(op,dst,imm=imm)

    def map(self,register,fd):
        self.emit(0x18,register,1,imm=fd)
        self.emit(0)

    def pointer(self,register,offset):
        self.emit(0xbf,register,10)
        self.emit(0x07,register,imm=offset)

    def lookup(self,fd,offset):
        self.map(1,fd)
        self.pointer(2,offset)
        self.emit(0x85,imm=1)

    def finish(self):
        for index,label in self.jumps:
            self.code[index][3]=self.labels[label]-index-1
        def signed(value):
            value&=0xffffffff
            return value-0x100000000 if value&0x80000000 else value
        return b''.join(struct.pack('<BBhi',op,(src<<4)|dst,off,signed(imm))
                        for op,dst,src,off,imm in self.code)


def socket_program(uid,owners,blocked,active_groups=None):
    a=Instructions()
    a.emit(0xbf,6,1)
    a.emit(0x85,imm=15)  # get_current_uid_gid
    a.emit(0xbc,7,0)    # zero-extend uid
    a.jump(0x55,7,uid,'allow')
    a.emit(0x85,imm=14)  # get_current_pid_tgid
    a.emit(0x77,0,imm=32)
    a.emit(0x7b,10,0,-16)
    a.emit(0xbf,1,6)
    a.emit(0x85,imm=46)  # get_socket_cookie
    a.jump(0x15,0,0,'allow')
    a.emit(0x7b,10,0,-8)
    a.map(1,owners)
    a.pointer(2,-8)
    a.pointer(3,-16)
    a.emit(0xb7,4,imm=0)
    a.emit(0x85,imm=2)
    a.lookup(blocked,-16)
    if active_groups is not None:
        a.jump(0x15,0,0,'allow')
        a.emit(0x79,1,0);a.emit(0x7b,10,1,-24)
        a.lookup(active_groups,-24)
    a.jump(0x55,0,0,'deny')
    a.label('allow')
    a.emit(0xb7,0,imm=1)
    a.emit(0x95)
    a.label('deny')
    a.emit(0xb7,0,imm=0)
    a.emit(0x95)
    return a.finish()


def packet_program(uid,owners,blocked,counts,direction,blocked_sockets=None,active_groups=None):
    a=Instructions()
    a.emit(0xbf,6,1)
    a.emit(0x85,imm=46)
    a.jump(0x15,0,0,'allow')
    a.emit(0x7b,10,0,-8)
    if blocked_sockets is not None:
        a.lookup(blocked_sockets,-8)
        a.jump(0x55,0,0,'deny')
    a.lookup(owners,-8)
    a.jump(0x15,0,0,'allow')
    a.emit(0x79,8,0)
    a.emit(0x7b,10,8,-48)
    a.lookup(blocked,-48)
    if active_groups is not None:
        a.jump(0x15,0,0,'measure')
        a.emit(0x79,1,0);a.emit(0x7b,10,1,-56)
        a.lookup(active_groups,-56)
    a.jump(0x55,0,0,'deny')
    a.label('measure')
    a.lookup(counts,-8)
    a.jump(0x55,0,0,'count')
    a.emit(0x7a,10,offset=-40,imm=0)
    a.emit(0x7a,10,offset=-32,imm=0)
    a.emit(0x7b,10,8,-24)
    a.emit(0x7a,10,offset=-16,imm=uid)
    a.map(1,counts)
    a.pointer(2,-8)
    a.pointer(3,-40)
    a.emit(0xb7,4,imm=1)  # BPF_NOEXIST: do not reset a racing counter
    a.emit(0x85,imm=2)
    a.lookup(counts,-8)
    a.jump(0x15,0,0,'allow')
    a.label('count')
    a.emit(0x61,1,6,0)  # __sk_buff.len
    a.emit(0xdb,0,1,0 if direction=='rx' else 8,0)  # atomic 64-bit add
    a.label('allow')
    a.emit(0xb7,0,imm=1)
    a.emit(0x95)
    a.label('deny')
    a.emit(0xb7,0,imm=0)
    a.emit(0x95)
    return a.finish()


def fork_program(blocked,active_groups,child_offset):
    """Inherit an active app block before the new task can create a socket."""
    a=Instructions();a.emit(0xbf,6,1)
    a.emit(0x85,imm=14);a.emit(0x77,0,imm=32);a.emit(0x7b,10,0,-8)
    a.emit(0x61,1,6,child_offset);a.emit(0x7b,10,1,-16)
    a.lookup(blocked,-8);a.jump(0x15,0,0,'clear')
    a.emit(0x79,1,0);a.emit(0x7b,10,1,-24)
    a.lookup(active_groups,-24);a.jump(0x15,0,0,'clear')
    a.map(1,blocked);a.pointer(2,-16);a.pointer(3,-24);a.emit(0xb7,4,imm=0)
    a.emit(0x85,imm=2);a.jump(0x05,0,0,'done')
    # A reused PID must never retain a previous application's inherited rule.
    a.label('clear');a.map(1,blocked);a.pointer(2,-16);a.emit(0x85,imm=3)
    a.label('done');a.emit(0xb7,0,imm=0);a.emit(0x95)
    return a.finish()


def fork_event():
    """Read tracepoint metadata without enabling a global tracing session."""
    import re
    def read(root):
        folder=root/'events/sched/sched_process_fork'
        identifier=int((folder/'id').read_text())
        text=(folder/'format').read_text()
        offset=re.search(r'field:[^;]*\bchild_pid;\s*offset:(\d+);\s*size:4;',text)
        if not offset:raise OSError(errno.ENOTSUP,'Unsupported process-fork tracepoint format')
        return identifier,int(offset.group(1))
    for root in (Path('/sys/kernel/tracing'),Path('/sys/kernel/debug/tracing')):
        try:return read(root)
        except FileNotFoundError:pass
    # Some desktops do not mount tracefs. Mount it only inside the helper's
    # private mount namespace; no host mount or tracing configuration changes.
    lib=ctypes.CDLL(None,use_errno=True)
    if lib.unshare(0x00020000):raise OSError(ctypes.get_errno(),'Cannot isolate process-fork tracing')
    lib.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_void_p]
    if lib.mount(None,b'/',None,16384|262144,None):raise OSError(ctypes.get_errno(),'Cannot isolate tracefs mounts')
    with tempfile.TemporaryDirectory(prefix='vitalux-network-trace-') as folder:
        target=os.fsencode(folder)
        if lib.mount(b'tracefs',target,b'tracefs',2|4|8,None):raise OSError(ctypes.get_errno(),'Process-fork tracing is unavailable')
        try:return read(Path(folder))
        finally:lib.umount2(ctypes.c_char_p(target),2)


class BPF:
    def __init__(self):
        machine=platform.machine().lower()
        self.number={'x86_64':321,'amd64':321,'aarch64':280}.get(machine)
        if self.number is None:raise OSError(errno.ENOTSUP,'Unsupported BPF architecture')
        self.lib=ctypes.CDLL(None,use_errno=True)
        self.lib.syscall.restype=ctypes.c_long
        self.fds=[]

    def call(self,command,attributes):
        buf=ctypes.create_string_buffer(attributes)
        value=self.lib.syscall(ctypes.c_long(self.number),ctypes.c_int(command),
                               ctypes.byref(buf),ctypes.c_uint(len(attributes)))
        if value<0:
            error=ctypes.get_errno()
            raise OSError(error,os.strerror(error))
        return value

    def map(self,value_size):
        fd=self.call(0,struct.pack('=IIIII',9,8,value_size,MAX_SOCKETS,0)+bytes(52))
        self.fds.append(fd)
        return fd

    def update(self,fd,key,value):
        k=ctypes.create_string_buffer(struct.pack('=Q',key))
        v=ctypes.create_string_buffer(value)
        self.call(2,struct.pack('=IIQQQ',fd,0,ctypes.addressof(k),ctypes.addressof(v),0))

    def delete(self,fd,key):
        k=ctypes.create_string_buffer(struct.pack('=Q',key))
        try:self.call(3,struct.pack('=IIQQQ',fd,0,ctypes.addressof(k),0,0))
        except OSError as exc:
            if exc.errno!=errno.ENOENT:raise

    def entries(self,fd,value_size):
        previous=None
        seen=set()
        for _ in range(MAX_SOCKETS):
            key=ctypes.create_string_buffer(struct.pack('=Q',previous or 0))
            nxt=ctypes.create_string_buffer(8)
            try:self.call(4,struct.pack('=IIQQQ',fd,0,ctypes.addressof(key) if previous is not None else 0,ctypes.addressof(nxt),0))
            except OSError as exc:
                if exc.errno==errno.ENOENT:break
                raise
            previous=struct.unpack('=Q',nxt.raw[:8])[0]
            if previous in seen:break
            seen.add(previous)
            value=ctypes.create_string_buffer(value_size)
            try:self.call(1,struct.pack('=IIQQQ',fd,0,ctypes.addressof(nxt),ctypes.addressof(value),0))
            except OSError as exc:
                if exc.errno==errno.ENOENT:continue
                raise
            yield previous,value.raw[:value_size]

    def program(self,code,kind,attach):
        instructions=ctypes.create_string_buffer(code)
        license_text=ctypes.create_string_buffer(b'Proprietary\0')
        log=ctypes.create_string_buffer(65536)
        attributes=bytearray(128)
        struct.pack_into('=IIQQIIQ',attributes,0,kind,len(code)//8,
                         ctypes.addressof(instructions),ctypes.addressof(license_text),1,len(log),ctypes.addressof(log))
        struct.pack_into('=I',attributes,68,attach)
        try:fd=self.call(5,bytes(attributes))
        except OSError as exc:
            reason=log.value.decode(errors='replace')[-4000:]
            raise OSError(exc.errno,f'{exc.strerror}; {reason}') from exc
        self.fds.append(fd)
        return fd

    def link(self,program,cgroup,attach):
        fd=self.call(28,struct.pack('=IIII',program,cgroup,attach,0)+bytes(48))
        self.fds.append(fd)

    def tracepoint(self,program,identifier):
        number={'x86_64':298,'amd64':298,'aarch64':241}[platform.machine().lower()]
        attributes=bytearray(128)
        struct.pack_into('=IIQQ',attributes,0,2,len(attributes),identifier,1)
        struct.pack_into('=Q',attributes,40,1)  # disabled until the BPF filter is attached
        online=Path('/sys/devices/system/cpu/online').read_text().strip()
        for part in online.split(','):
            bounds=[int(value) for value in part.split('-')]
            for cpu in range(bounds[0],bounds[-1]+1):
                raw=ctypes.create_string_buffer(bytes(attributes))
                fd=self.lib.syscall(ctypes.c_long(number),ctypes.byref(raw),ctypes.c_int(-1),
                                    ctypes.c_int(cpu),ctypes.c_int(-1),ctypes.c_ulong(8))
                if fd<0:
                    error=ctypes.get_errno()
                    if error==errno.ENODEV:continue
                    raise OSError(error,'Cannot attach process-fork protection: '+os.strerror(error))
                self.fds.append(fd)
                fcntl.ioctl(fd,0x40042408,program)
                fcntl.ioctl(fd,0x2400,0)
                # Tracepoint programs attach to the global event, not just
                # this perf event's CPU. A second attachment returns EEXIST.
                return
        raise OSError(errno.ENODEV,'No online CPU is available for process-fork protection')

    def close(self):
        for fd in reversed(self.fds):
            try:os.close(fd)
            except OSError:pass
        self.fds.clear()


class NetworkSession:
    def __init__(self,uid):
        self.uid=uid
        self.bpf=BPF()
        self.rules=set()
        self.rule_groups={}
        self.active_rule_groups=set()
        self.connection_rules={}
        self.blocked_pids=set()
        self.metadata={}
        self.owner_pids={}
        self.counter_pids={}
        self.base=None
        try:
            self.owners=self.bpf.map(8)
            self.blocked=self.bpf.map(8)
            self.active_groups=self.bpf.map(8)
            self.counts=self.bpf.map(32)
            self.blocked_sockets=self.bpf.map(8)
            group=os.open('/sys/fs/cgroup',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
            self.bpf.fds.append(group)
            self.refresh()
            for code,kind,attach in ((socket_program(uid,self.owners,self.blocked,self.active_groups),9,2),
                (packet_program(uid,self.owners,self.blocked,self.counts,'rx',self.blocked_sockets,self.active_groups),8,0),
                (packet_program(uid,self.owners,self.blocked,self.counts,'tx',self.blocked_sockets,self.active_groups),8,1)):
                program=self.bpf.program(code,kind,attach)
                self.bpf.link(program,group,attach)
            identifier,offset=fork_event()
            self.bpf.tracepoint(self.bpf.program(fork_program(self.blocked,self.active_groups,offset),5,0),identifier)
        except BaseException:
            self.bpf.close()
            raise

    def refresh(self):
        self.base=socket_snapshot(self.uid)
        self.apps=self.base['applications']
        for key in self.rules:
            if key not in self.rule_groups:self.rule_groups[key]=len(self.rule_groups)+1
        active={self.rule_groups[key]:key for key in self.rules}
        for group in self.active_rule_groups-set(active):self.bpf.delete(self.active_groups,group)
        for group in set(active)-self.active_rule_groups:self.bpf.update(self.active_groups,group,struct.pack('=Q',1))
        self.active_rule_groups=set(active)
        members={pid:struct.unpack('=Q',raw)[0] for pid,raw in self.bpf.entries(self.blocked,8)}
        for pid,group in list(members.items()):
            app=self.apps.get(pid) or application(pid,self.uid)
            if group not in active or app is None:
                self.bpf.delete(self.blocked,pid);members.pop(pid,None)
                continue
            app['key']=active[group]
            self.apps[pid]=app
        for pid,app in self.apps.items():
            group=self.rule_groups.get(app['key']) if app['key'] in self.rules else None
            if group and members.get(pid)!=group:
                self.bpf.update(self.blocked,pid,struct.pack('=Q',group));members[pid]=group
        self.blocked_pids=set(members)
        for row in self.base['connections']:
            pid=row.get('pid')
            if not pid:continue
            if pid in members:row['key']=active[members[pid]]
            cookie=row['cookie']
            if cookie<=0:continue  # proc fallback has no kernel socket cookie
            self.metadata[cookie]={key:row[key] for key in ('pid','start','name','exe','key')}
            if self.owner_pids.get(cookie)!=pid:
                self.bpf.update(self.owners,cookie,struct.pack('=Q',pid))
                self.owner_pids[cookie]=pid
        if len(self.owner_pids)>MAX_SOCKETS:
            current={row['cookie'] for row in self.base['connections']}
            self.owner_pids={key:value for key,value in self.owner_pids.items() if key in current}
            self.metadata={key:value for key,value in self.metadata.items() if key in current}
        live={row['cookie']:(row.get('pid'),row.get('start')) for row in self.base['connections']}
        for cookie,identity in list(self.connection_rules.items()):
            if live.get(cookie)!=identity:
                self.bpf.delete(self.blocked_sockets,cookie);self.connection_rules.pop(cookie,None)

    def connection_rule(self,request):
        cookie=request.get('cookie');pid=request.get('pid');start=request.get('start')
        if type(cookie) is not int or cookie<=0 or type(pid) is not int or type(start) is not int:
            raise ValueError('Invalid connection identity')
        self.refresh()
        app=application(pid,self.uid)
        row=next((r for r in self.base['connections'] if r['cookie']==cookie and r.get('pid')==pid and r.get('start')==start),None)
        if not app or app['start']!=start or row is None:raise ValueError('The selected connection has ended or changed')
        if request['op']=='block_connection':
            self.bpf.update(self.blocked_sockets,cookie,struct.pack('=Q',1))
            self.connection_rules[cookie]=(pid,start)
        else:
            self.bpf.delete(self.blocked_sockets,cookie);self.connection_rules.pop(cookie,None)

    def rule(self,request):
        if request['op']=='allow' and isinstance(request.get('key'),str) and request['key'] in self.rules:
            self.rules.discard(request['key'])
            self.refresh()
            return request['key']
        pid=request.get('pid')
        start=request.get('start')
        if type(pid) is not int or type(start) is not int:raise ValueError('Invalid process identity')
        app=application(pid,self.uid)
        if not app or app['start']!=start or not app['exe']:
            raise ValueError('The selected process has ended or changed')
        self.refresh()
        live=application(pid,self.uid)
        if not live or live['start']!=start:
            raise ValueError('The selected process has ended or changed')
        app=self.apps.get(pid,app)
        if app['start']!=start:raise ValueError('The selected process has ended or changed')
        if request['op']=='block':self.rules.add(app['key'])
        else:self.rules.discard(app['key'])
        self.refresh()
        return app['key']

    def snapshot(self):
        counters=[]
        for cookie,raw in self.bpf.entries(self.counts,32):
            rx,tx,pid,uid=struct.unpack('=QQQQ',raw)
            if uid!=self.uid:continue
            app=self.metadata.get(cookie)
            if app is None:
                app=self.apps.get(pid)
                if app:self.metadata[cookie]=dict(app)
            counters.append(dict(cookie=cookie,rx=rx,tx=tx,**(app or dict(
                pid=None,start=None,name='',exe='',key='@unassigned'))))
        base=dict(self.base)
        base.update(backend='bpf',counters=counters,monotonic=time.monotonic(),rules=sorted(self.rules),
                    connection_rules=sorted(self.connection_rules))
        return base

    def close(self):self.bpf.close()


def helper_main():
    if sys.argv[1:]!=['--session'] or os.geteuid()!=0:
        raise SystemExit('This helper must be authenticated with pkexec --session')
    # pkexec supplies this value itself; root-only operation is not delegated.
    raw=os.environ.get('PKEXEC_UID','')
    if not raw.isdecimal() or not 0<int(raw)<2**31:
        raise SystemExit('Missing authenticated desktop user')
    uid=int(raw)
    sys.dont_write_bytecode=True
    def send(value):
        data=json.dumps(value,separators=(',',':'),ensure_ascii=True)
        sys.stdout.write(data+'\n')
        sys.stdout.flush()
    session=None
    try:
        session=NetworkSession(uid)
        send(dict(type='ready',uid=uid,backend='bpf'))
        buffer=b''
        next_sample=0.
        while True:
            readable,_,_=select.select([sys.stdin.fileno()],[],[],max(0,min(.25,next_sample-time.monotonic())))
            if readable:
                chunk=os.read(sys.stdin.fileno(),4096)
                if not chunk:break
                buffer+=chunk
                if len(buffer)>MAX_MESSAGE:raise ValueError('Command exceeds limit')
                while b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    try:
                        command=json.loads(line)
                        if not isinstance(command,dict):raise ValueError('Invalid command')
                        op=command.get('op')
                        if op=='quit':return
                        if op=='clear':
                            session.rules.clear()
                            for cookie in list(session.connection_rules):session.bpf.delete(session.blocked_sockets,cookie)
                            session.connection_rules.clear()
                            session.refresh()
                            send(dict(type='rules',rules=[],connection_rules=[]))
                        elif op in ('block','allow'):
                            session.rule(command)
                            send(dict(type='rules',rules=sorted(session.rules),connection_rules=sorted(session.connection_rules)))
                        elif op in ('block_connection','allow_connection'):
                            session.connection_rule(command)
                            send(dict(type='rules',rules=sorted(session.rules),connection_rules=sorted(session.connection_rules)))
                        else:raise ValueError('Unknown command')
                    except (OSError,ValueError,TypeError) as exc:
                        send(dict(type='command_error',error=str(exc)[:500]))
            if time.monotonic()>=next_sample:
                session.refresh()
                send(dict(type='sample',data=session.snapshot()))
                next_sample=time.monotonic()+1
    except (OSError,ValueError) as exc:
        try:send(dict(type='error',error=str(exc)[:4000]))
        except (BrokenPipeError,OSError):pass
    except BrokenPipeError:pass
    finally:
        if session is not None:session.close()


if __name__=='__main__':
    helper_main()
