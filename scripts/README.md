# 开发脚本

保存仓库结构、格式、合同和本地环境验证脚本。脚本不能修改旧项目与 KF RAG 参考资产。

- `python scripts/milvus_scan.py --archive <导出镜像.tar> --report <完整Trivy报告.json> --image-id <Docker镜像ID>`：只读验证 Milvus 候选镜像归档与报告的关联，同时要求 Ubuntu 和两个指定 Go 制品都有扫描结果。通过只代表该报告满足漏洞门禁，不代表扫描来源可信、证据仍有效、运行兼容或获准部署；调用方须使用固定扫描器生成报告并另行完成其余验证。见 [候选构建记录](../docs/testing/m01-milvus-build-candidate.md)。

- `python scripts/verify_implementation_standards.py`：只读核对四项实施标准的规则编号、80 个验收编号、关联规则、JSON 示例、表格与本地链接。检查通过只表示文档结构一致，不表示业务验收通过。
