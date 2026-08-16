"""dsh-mechanics-lab 的共享脚手架。

这里只放**基础设施**（进程编排、YAML 解析、断言辅助），不放**素材**。
每一课的教学插件放在各自实验目录的 fixtures/ 下，允许重复 —— 那是特性不是缺陷：
读者打开一个实验目录就能看到完整的一课，改一个实验也弄不坏另一个。
"""

from .core import (
    BUNDLE_BASE,
    BUNDLE_WEB,
    EXPERIMENTS_DIR,
    FORBIDDEN_PORTS,
    LAB_PORT_RANGE,
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    RESULTS_DIR,
    TESTHOME_ROOT,
    LabError,
    LabHome,
    LabProfile,
    dsh_bin,
    make_junction,
    rmtree_safe,
)
from .dump import DumpResult, JsExpr, dump_config
from .instance import Instance, acquire_lock, assert_ports_free, http_get, port_listening, release_lock, start_instance

__all__ = [
    "BUNDLE_BASE",
    "BUNDLE_WEB",
    "EXPERIMENTS_DIR",
    "FORBIDDEN_PORTS",
    "LAB_PORT_RANGE",
    "LAB_ROOT",
    "PKG_HMR",
    "PKG_TIMER",
    "RESULTS_DIR",
    "TESTHOME_ROOT",
    "DumpResult",
    "Instance",
    "JsExpr",
    "LabError",
    "LabHome",
    "LabProfile",
    "acquire_lock",
    "assert_ports_free",
    "dsh_bin",
    "dump_config",
    "http_get",
    "make_junction",
    "port_listening",
    "release_lock",
    "rmtree_safe",
    "start_instance",
]
