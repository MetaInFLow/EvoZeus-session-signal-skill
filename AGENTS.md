# AGENTS.md

## 项目约定

- 项目产出文件默认用中文，关键专有名词、专业名词可以用英文。
- Feishu 相关的操作用 `larkcli`。
- 本 repo 属于 EvoZeus repo 体系，归属 `metainflow private`。

## Repo 职责

- 维护稳定的 Python OfficialFactor 抽象契约。
- 维护官方 Factor spec schema 和 official factors。
- 不承接真实业务 Factor pack、promotion candidate、release manifest、checksum、SBOM 或 attestation。

## Agent 入口

- Official release 相关任务先读 `SKILL.md` 和 `README.md`。
- 只在要修改官方 Factor contract、schema 或 official factors 时从本 repo 开始。
- 真实执行、安装、扫描和 report 输出属于 infra。
