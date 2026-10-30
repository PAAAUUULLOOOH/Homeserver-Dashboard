"""Keep decoded images within a byte budget without changing their resolution."""
from collections import OrderedDict, namedtuple
from functools import wraps


class ImageCache(OrderedDict):
    def __init__(self, max_bytes=24*1024*1024, max_entries=16):
        super().__init__()
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.bytes = 0

    @staticmethod
    def cost(image):
        return image.width()*image.height()*max(1, image.depth()//8)

    def get(self, key, default=None):
        if key not in self:return default
        self.move_to_end(key)
        return super().__getitem__(key)

    def __setitem__(self, key, image):
        if key in self:self.bytes -= self.cost(super().pop(key))
        size = self.cost(image)
        if size > self.max_bytes:return
        while self and (self.bytes+size > self.max_bytes or len(self) >= self.max_entries):
            self.bytes -= self.cost(super().popitem(last=False)[1])
        super().__setitem__(key, image)
        self.bytes += size

    def clear(self):
        super().clear()
        self.bytes = 0


def cached_images(max_bytes, max_entries=6):
    def decorate(function):
        cache=ImageCache(max_bytes,max_entries);counts=[0,0]
        stats=namedtuple('ImageCacheInfo','hits misses entries bytes max_bytes')
        @wraps(function)
        def cached(*args):
            image=cache.get(args)
            if image is not None:counts[0]+=1;return image
            counts[1]+=1;image=function(*args);cache[args]=image
            return image
        def clear():cache.clear();counts[:]=[0,0]
        cached.cache_clear=clear
        cached.cache_info=lambda:stats(*counts,len(cache),cache.bytes,cache.max_bytes)
        return cached
    return decorate

