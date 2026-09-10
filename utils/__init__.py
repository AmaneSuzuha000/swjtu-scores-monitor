"""SWJTU 成绩监控的工具包。

没有这个 __init__.py 时，utils 只是**命名空间包**；Python 的导入规则是
“正式包（含 __init__.py）优先于命名空间包”，因此只要运行环境的 sys.path
里存在另一个同名的正式 utils 包（例如某些工具通过 .pth 注入的 src 目录），
`import utils.fetcher` 就会解析到那个包并报 ModuleNotFoundError。
显式声明为正式包即可稳定胜出。
"""
