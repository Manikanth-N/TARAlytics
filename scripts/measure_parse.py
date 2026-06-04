import resource, time, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.log_parser import DataFlashParser
tag = sys.argv[1]; path = f'logs/000000{tag}.BIN'; mb = os.path.getsize(path)/1e6
t = time.perf_counter(); r = DataFlashParser().parse(path); dt = time.perf_counter()-t
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024.0
print(f'{tag}: {mb:.0f}MB  parse {dt:.2f}s  peakRSS {rss:.0f}MB ({rss/mb:.2f}x)  rows {sum(len(v) for v in r.values()):,}')
