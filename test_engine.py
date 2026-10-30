import base64
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import unittest

from engine import Engine,EngineError,TEMPLATES


class FakeDocker:
    def __init__(self):self.calls=[];self.running=False;self.owner=''
    def __call__(self,args,**kwargs):
        self.calls.append(args)
        command=args[2:];out=''
        if command[0]=='create':
            self.owner=next(x.split('=',1)[1] for x in command if x.startswith('io.vitalux.dashboard.id='));out='container-id'
        if command[0]=='inspect':
            out=json.dumps({'io.vitalux.dashboard.id':self.owner}) if 'Labels' in command[2] else str(self.running).lower()
        if command[0]=='start':self.running=True
        if command[0]=='stop':self.running=False
        if command[0]=='ps' and self.owner:out=json.dumps(dict(Names='vitalux-'+self.owner,State='running' if self.running else 'exited',Status='Up' if self.running else 'Exited')) if '{{json .}}' in command else 'vitalux-'+self.owner
        return subprocess.CompletedProcess(args,0,out,'')


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.fake=FakeDocker();self.engine=Engine(self.root,runner=self.fake)
    def tearDown(self):self.engine.pool.shutdown(wait=True);self.temp.cleanup()
    def wait_job(self,result):
        job=self.engine.jobs[result['job_id']]
        for _ in range(300):
            if job['status']!='running':return job
            time.sleep(.01)
        self.fail('Job timeout')
    def install(self,**options):
        result=self.engine.install(dict(template='minecraft',name='Testwelt',accept_license=True,**options));job=self.wait_job(result);self.assertEqual(job['status'],'done',job);return self.engine.servers[0]
    def test_license_and_template_validation_have_no_docker_side_effect(self):
        for data in [dict(template='minecraft',name='A'),dict(template='unknown',name='A',accept_license=True)]:
            with self.assertRaises(EngineError):self.engine.install(data)
        self.assertEqual(self.fake.calls,[])
    def test_install_allowlist_and_no_privileged_or_docker_mount(self):
        s=self.install(variant='FABRIC',port=25577)
        call=next(c for c in self.fake.calls if c[2]=='create')
        self.assertIn('itzg/minecraft-server:java21',call);self.assertIn('TYPE=FABRIC',call);self.assertIn('25577:25565/tcp',call)
        self.assertNotIn('--privileged',call);self.assertNotIn('--network=host',call)
        self.assertFalse(any('/var/run/docker.sock' in x for x in call[3:]))
        self.assertNotIn('env',self.engine.list()[0])
        self.assertEqual(self.engine.list()[0]['status'],'running')
    def test_port_collision_rejected(self):
        self.install()
        with self.assertRaisesRegex(EngineError,'Port'):self.engine.install(dict(template='minecraft',name='Zweite Welt',accept_license=True))
    def test_hostile_command_is_one_argument_not_a_shell(self):
        s=self.install();payload='say hi; $(touch /tmp/never-execute)'
        self.engine.action(s['id'],'command',dict(command=payload))
        self.assertEqual(self.fake.calls[-1][-1],payload)
    def test_foreign_container_rejected(self):
        s=self.install();self.fake.owner='someone-else'
        with self.assertRaisesRegex(EngineError,'gehört'):self.engine.action(s['id'],'command',dict(command='list'))
    def test_backup_requires_stopped_container(self):
        s=self.install();job=self.wait_job(self.engine.action(s['id'],'backup'));self.assertEqual(job['status'],'error');self.assertIn('stoppen',job['error'])
    def test_backup_restore_and_mod_toggle_keep_data(self):
        s=self.install();self.fake.running=False;folder=self.engine._directory(s);(folder/'world.txt').write_text('old world')
        result=self.engine.backup(s);(folder/'world.txt').write_text('new world')
        self.engine.restore(s,result['backup']);self.assertEqual((folder/'world.txt').read_text(),'old world')
        self.engine.change_mod(s['id'],dict(action='upload',name='test.jar',data=base64.b64encode(b'PK\x03\x04test-jar').decode()))
        self.engine.change_mod(s['id'],dict(action='toggle',name='test.jar'))
        self.assertTrue((folder/'plugins/test.jar.disabled').is_file());self.assertGreaterEqual(len(self.engine.backups(s['id'])),3)
    def test_restore_rejects_path_escape_before_touching_server(self):
        s=self.install();folder=self.root/'backups'/s['id'];folder.mkdir(parents=True)
        path=folder/'backup-20261029-100000-abcd.tar.gz'
        with tarfile.open(path,'w:gz') as tar:
            info=tarfile.TarInfo('server/../../outside');info.size=1;tar.addfile(info,io.BytesIO(b'x'))
        with self.assertRaises(EngineError):self.engine.restore(s,path.name)
        self.assertFalse((self.root/'outside').exists())
    def test_symlinks_are_excluded_from_backup_and_rejected_for_mods(self):
        s=self.install();self.fake.running=False;folder=self.engine._directory(s);(folder/'world').write_text('hello');(folder/'escape').symlink_to('/etc')
        result=self.engine.backup(s)
        with tarfile.open(self.root/'backups'/s['id']/result['backup']) as tar:self.assertNotIn('server/escape',tar.getnames())
        (folder/'plugins').symlink_to(self.root)
        with self.assertRaises(EngineError):self.engine.mods(s['id'])
    def test_failing_pull_is_error_not_a_success(self):
        def fail(args,**kwargs):return subprocess.CompletedProcess(args,1,'','download failed')
        self.engine.runner=fail
        job=self.wait_job(self.engine.preload('minecraft'));self.assertEqual(job['status'],'error');self.assertIn('download failed',job['error'])
    def test_preloading_does_not_accept_license_or_create_server(self):
        self.wait_job(self.engine.preload('teamspeak'));self.assertEqual(self.engine.servers,[]);self.assertEqual(self.fake.calls[0][2:],['pull',TEMPLATES['teamspeak']['image']])
    def test_invalid_ids_and_mod_paths(self):
        with self.assertRaises(EngineError):self.engine.action('../../etc','start')
        s=self.install();self.fake.running=False
        with self.assertRaises(EngineError):self.engine.change_mod(s['id'],dict(action='upload',name='../oops.jar',data='UEsDBA=='))


if __name__=='__main__':unittest.main()
