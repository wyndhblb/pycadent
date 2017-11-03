from __future__ import absolute_import
from __future__ import print_function
import time
import math
import msgpack
import requests
from structlog import get_logger
logger = get_logger()

try:
    from graphite_api.intervals import Interval, IntervalSet
    from graphite_api.node import LeafNode, BranchNode
except ImportError:
    from graphite.intervals import Interval, IntervalSet
    from graphite.node import LeafNode, BranchNode


__all__ = ["CadentLeafNode", "CadentReader", "CadentFinder"]


MAX_POINTS = 4096
HOSTCACHEMAP = {}  # list of targets -> cache host

urls = None
urllength = 8000


def chunk(nodelist, length):
    chunklist = []
    linelength = 0
    for node in nodelist:
        # the magic number 8 is because the nodes list gets padded
        # with '&target=' in the resulting request
        nodelength = len(str(node)) + 8

        if linelength + nodelength > length:
            yield chunklist
            chunklist = [node]
            linelength = nodelength
        else:
            chunklist.append(node)
            linelength += nodelength
    yield chunklist


class CadentLeafNode(LeafNode):
    __fetch_multi__ = 'cadent'
    __slots__ = ('host',)


class HostList(object):
    __slots__ = ('len', 'idx', 'hosts',)

    def __init__(self, hosts):
        self.hosts = hosts
        self.len = len(hosts)
        self.idx = 0

    def at_end(self):
        return self.idx == self.len

    def at_start(self):
        return self.idx == 0

    def on_host(self):
        return self.hosts[self.idx]

    def next(self):
        if self.at_end():
            self.idx = 0
        g = self.hosts[self.idx]
        self.idx += 1
        return g


class URLs(object):

    def __init__(self, hosts):
        self.hosts = hosts
        self.iterator = HostList(hosts)

    @property
    def on_host(self):
        return self.iterator.on_host()

    @property
    def host(self):
        return self.iterator.next()

    @property
    def paths(self):
        return '{0}/paths'.format(self.host)

    def paths_for_host(self, host):
        return '{0}/paths'.format(host)

    @property
    def metrics(self):
        return '{0}/metrics'.format(self.host)

    def metrics_for_host(self, host):
        return '{0}/metrics'.format(host)

    @property
    def cache(self):
        return '{0}/cache'.format(self.host)


class CadentReader(object):
    __slots__ = ('path', 'host',)

    def __init__(self, path, host):
        self.path = path
        self.host = host

    def fetch(self, start_time, end_time):
        u = urls.metrics
        if self.host:
            u = urls.metrics_for_host(self.host)
            
        data = msgpack.unpackb(requests.get(
            u,
            params={
                'target': self.path,
                'from': start_time,
                'to': end_time,
                'format': 'msgpack'
            }
        ).content, encoding="utf8")

        if not data or not data.get('start') or not data.get('end'):
            return (start_time, end_time, end_time - start_time), []

        time_info = data.get('start'), data.get('end'), data.get('step')

        for k, v in data.get('series', {}).items():
            if k == self.path:
                _data = list(map(
                    lambda x: x['value'] if not math.isnan(
                        x['value']) else None,
                    v.get('data', [])
                ))
                break

        return time_info, _data

    def get_intervals(self):
        return IntervalSet([Interval(0, int(time.time()))])


class CadentFinder(object):
    __fetch_multi__ = 'cadent'

    def __init__(self, config=None):
        global urls
        global urllength
        if config is not None:
            if 'urls' in config['cadent']:
                urls = config['cadent']['urls']
            else:
                urls = [config['cadent']['url'].strip('/')]
            if 'urllength' in config['cadent']:
                urllength = config['cadent']['urllength']
        else:
            from django.conf import settings
            urls = getattr(settings, 'CADENT_URLS')
            if not urls:
                urls = [settings.CADENT_URL]
            urllength = getattr(settings, 'CADENT_URL_LENGTH', urllength)
        urls = URLs(urls)
        
    def find_nodes(self, query):
        logger.debug("find", query=query)
        pthhave = {}
        
        for h in urls.hosts:
            try:
                pths = msgpack.unpackb(requests.get(
                    urls.paths_for_host(h),
                    params={'query': query.pattern, 'format': 'msgpack'}
                ).content, encoding="utf8")
            except Exception as excp:
                logger.error("error in find {}".format(excp))
                continue
                 
            for path in pths:
                # skip any dupes
                if path['path'] in pthhave:
                    continue
                
                pthhave[path['path']] = 1
                if path.get('leaf', False):
                    yield CadentLeafNode(
                        path['path'],
                        CadentReader(path['path'], h)
                    )
                else:
                    yield BranchNode(path['path'])
        
            raise StopIteration

    def _fetch_one_metric(self, host, node, start_time, end_time, mpts):

        # msgpack is fine here too, only one series
        # speed difference is in the big series blobs
        data = msgpack.unpackb(requests.get(
            urls.metrics_for_host(host),
            params={
                'target': node,
                'from': start_time,
                'to': end_time,
                'max_points': mpts,
                'format': 'msgpack'
            }
        ).content, encoding="utf8")

        return data

    def fetch_until_cache(self, node, start_time, end_time, mpts):
        i = 0
        for h in urls.hosts:
            i += 1
            gots = self._fetch_one_metric(h, node, start_time, end_time, mpts)
            if not gots:
                continue
            for _, s in gots.get('series', {}).items():
                # no cache in use, no need to continue
                if not s.get('using_cache', False):
                    return gots

                # this is the node for the cache, so use it
                if s.get('in_cache', False):
                    return gots

                # no more to try, just move on
                if i == len(urls.hosts):
                    return gots

    def fetch_multi(self, nodes, start_time, end_time):

        paths = [node.path for node in nodes]
        data = {}
        time_info = None

        # to make all things nicer we are going to requests a max point
        # limit, as w/o that, we can easily get back many GB of data
        # and thus break alot of things in RAM space
        # if we assume a "smallest" res of 1s, we just make sure not to get any
        # more then MAX_POINTS
        mpts = MAX_POINTS
        if end_time - start_time < MAX_POINTS:
            mpts = ""

        for pathlist in chunk(paths, urllength):
            tmpdata = msgpack.unpackb(requests.get(
                urls.metrics,
                params={
                    'target': pathlist,
                    'from': start_time,
                    'to': end_time,
                    'max_points': mpts,
                    'format': 'msgpack'
                }
            ).content, encoding="utf8")

            d = tmpdata
            if not d.get('series', []):
                continue

            if not time_info:
                time_info = d['start'], d['end'], d['step']
                data['series'] = {}

            # need to remove the "extra" time stamp item
            sers = {}
            for k, s in d.get('series', {}).items():

                # if this item is NOT in the cache, it means we have picked
                # the wrong host for data, so we need to go find it again
                if s.get('using_cache', False) and not s.get('in_cache', False):

                    # this one is msgpack
                    aux_data = self.fetch_until_cache(
                        s.get('target'),
                        start_time,
                        end_time,
                        mpts
                    )
                    if aux_data and aux_data.get('series'):
                        for k, s in aux_data['series'].items():
                            _data = list(map(
                                lambda x: x['value'] if not math.isnan(
                                    x['value']) else None,
                                s.get('data', [])
                            ))
                            sers[k] = _data
                else:
                    _data = list(map(
                        lambda x: x['value'] if not math.isnan(
                            x['value']) else None,
                        s.get('data', [])
                    ))
                    sers[k] = _data
            data['series'].update(sers)

        if not time_info:
            return (start_time, end_time, end_time - start_time), {}

        return time_info, data['series']
