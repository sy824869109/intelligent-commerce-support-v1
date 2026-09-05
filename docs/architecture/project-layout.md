# 项目目录

```text
.
├─ .github/
│  └─ pull_request_template.md
├─ apps/
│  ├─ web-customer/
│  ├─ web-agent/
│  ├─ web-admin/
│  ├─ api-gateway/
│  ├─ commerce-service/
│  ├─ conversation-service/
│  ├─ orchestration-service/
│  ├─ knowledge-service/
│  ├─ ticket-service/
│  └─ worker/
├─ packages/
│  ├─ contracts/
│  ├─ domain/
│  ├─ observability/
│  └─ testing/
├─ deploy/
│  ├─ compose/
│  ├─ nginx/
│  ├─ mysql/
│  └─ scripts/
├─ docs/
│  ├─ api/
│  ├─ architecture/
│  ├─ baseline/
│  ├─ decisions/
│  ├─ operations/
│  ├─ progress/
│  └─ testing/
├─ tests/
│  ├─ contract/
│  ├─ integration/
│  ├─ e2e/
│  ├─ performance/
│  └─ security/
├─ scripts/
├─ CHANGELOG.md
├─ CONTRIBUTING.md
├─ SECURITY.md
└─ VERSION
```

每个目录使用 README 声明职责。后续实现只能在所属模块内增加源码；出现新的跨模块职责时，先更新模块边界并提交 ADR。
