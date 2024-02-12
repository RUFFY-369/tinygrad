import unittest
from tinygrad import Tensor, GlobalCounters
from tinygrad.helpers import Timing, CI, Profiling, WINO, DEBUG
from tinygrad.ops import LoadOps
from tinygrad.codegen.linearizer import Linearizer
from tinygrad.realize import run_schedule

class TestWinograd(unittest.TestCase):
  def setUp(self):
    self.old = WINO.value
    WINO.value = 1
  def tearDown(self):
    WINO.value = self.old

  def test_speed(self):
    x = Tensor.empty(1,4,9,9)
    w = Tensor.empty(4,4,3,3)

    with Timing("running conv: "):
      out = Tensor.conv2d(x, w)

    with Timing("scheduling: "):
      sched = out.lazydata.schedule()

    for i,s in enumerate(sched):
      if s.ast.op in LoadOps: continue
      ops = s.ast.lazyops
      with Timing(f"linearize {i} with {len(ops):4d} ops: "):
        l = Linearizer(s.ast)
        l.hand_coded_optimizations()
        l.linearize()
      assert len(l.sts) <= 256  # just the current value to prevent regression
      if DEBUG >= 2: print(f"{len(l.sts):4d} shapetrackers with max {max(len(x.views) for x in l.sts)} views")
      for st in l.sts:
        assert len(st.views) <= 2, "too many views in winograd"
        if DEBUG >= 3:
          print(f"{len(st.views):3d} views")
          for v in st.views: print(v)

  def test_profile(self):
    x,w = Tensor.rand(1,4,9,9).realize(), Tensor.rand(4,4,3,3).realize()
    with Profiling(enabled=not CI, sort='time'):
      out = Tensor.conv2d(x,w).realize()
    out.numpy()

  def test_four_kernels(self):
    x,w = Tensor.rand(1,4,9,9).realize(), Tensor.rand(4,4,3,3).realize()
    GlobalCounters.reset()
    out = Tensor.conv2d(x,w).realize()
    assert GlobalCounters.kernel_count == 4
    out.numpy()

  def test_counters(self):
    IC, OC, X, Y = 4,4,9,9
    #OC, IC, X, Y = 512, 256, 8, 8
    x,w = Tensor.rand(1,IC,Y,X).realize(), Tensor.rand(OC,IC,3,3).realize()
    WINO.value = 0
    GlobalCounters.reset()
    Tensor.conv2d(x,w).realize()
    ops_normal, mem_normal = GlobalCounters.global_ops, GlobalCounters.global_mem
    WINO.value = 1
    GlobalCounters.reset()
    sched = Tensor.conv2d(x,w).lazydata.schedule()
    run_schedule(sched[0:1])
    print(sched[0].out.shape)
    print(GlobalCounters.global_ops, GlobalCounters.global_mem)

    run_schedule(sched[1:])
    ops_wino, mem_wino = GlobalCounters.global_ops, GlobalCounters.global_mem
    print("ops: normal", ops_normal, "wino", ops_wino, "ratio", ops_wino/ops_normal)
    print("mem: normal", mem_normal, "wino", mem_wino, "ratio", mem_wino/mem_normal)
    #assert ops_wino < ops_normal
    #assert mem_wino < mem_normal

if __name__ == '__main__':
  unittest.main(verbosity=2)