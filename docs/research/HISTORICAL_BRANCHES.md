# SwarmBalance 历史分支与代码来源登记（2026-10-18）

**目的**：保留 Git SHA、PR 和代码来源；用于分支归档，不等于所有旧实现都已成为当前稳定功能。

- 登记基准：`master@703ef8a26ad032af3b5ccd30d027c0bd72345d2a`，65 条旧分支（不含 master 与临时集成候选）；研究累计主线已通过 [PR #65](https://github.com/159357yangjun/SwarmBalance/pull/65) 进入 master。
- **A 类**：提交全部可由主线历史抵达。关闭冗余 PR 不损失代码来源。
- **B 类**：后端项目/运行 API 在 [PR #66](https://github.com/159357yangjun/SwarmBalance/pull/66) 单独兼容集成；**否定的四表单 UI 不进入默认界面**。
- **C、G 类**：部分独有提交是 RED 见证、比较或互斥代码；保留原始 PR/固定 SHA，不直接覆盖已验证内核。研究结论索引见 [研究 README](README.md)。
- **D、E、F 类**：文档/规则工具不等于仿真引擎。其历史状态与 PR 可追溯；未获工程确认的 ARCH/CONTRACT 不自动升级为稳定接口。
- GitHub 分支删除前确认 PR 来源引用和不可替代代码已归档；**删除分支≠删除 GitHub PR、SHA 或历史证据**，但 GitHub 不保证未引用悬空对象永存。独有实现尚未纳入主线时应保留受保护的代码备份或 PR 引用。

## A. 提交已经完整进入 master（29 条）

| 分支（固定来源） | Head SHA | GitHub PR |
|---|---|---|
| `audit/model-provenance-and-paired-plan-v1` | `b23a8e4362260acb6a0df330fbd8665581d0e567` | [#36](https://github.com/159357yangjun/SwarmBalance/pull/36) |
| `ci-validation` | `34cf506ea9b0871fba395e47df6dc96b3a2a21b0` | [#1](https://github.com/159357yangjun/SwarmBalance/pull/1) |
| `integration/research-mainline-20261018` | `70c2ad08dd316bdd60e580c613c3af50445568e6` | [#65](https://github.com/159357yangjun/SwarmBalance/pull/65) |
| `logic/l1-task-lifecycle-delivery-proof-v1` | `f1bf21cc42f2566b2981a1a6092cbedf215db809` | [#41](https://github.com/159357yangjun/SwarmBalance/pull/41) |
| `p1-b-onboard-energy-experiment` | `04937f6d08c11ec14c8c1c47e433d75de5b04ca5` | [#2](https://github.com/159357yangjun/SwarmBalance/pull/2) |
| `p1-b-paired-analysis-v1` | `47c6e4582cd175151769ae8dd68383da805d3b3c` | [#5](https://github.com/159357yangjun/SwarmBalance/pull/5) |
| `p1-b-pressure-event-validation` | `7c5cc2745ae380278ef75c71271bb530e653d87e` | [#3](https://github.com/159357yangjun/SwarmBalance/pull/3) |
| `p1-b-shadow-ledger-v1` | `d71d0f81cb44c896b0845e43eb82e42874cf0c6d` | [#6](https://github.com/159357yangjun/SwarmBalance/pull/6) |
| `p1-b-stress-grid-v1` | `f0f70f553dba76b54b02acc835561af1b8c4a25a` | [#4](https://github.com/159357yangjun/SwarmBalance/pull/4) |
| `p2-1-low-energy-audit-v1` | `806d07653af52b83202ba232cb1f3e88dd9b7901` | [#7](https://github.com/159357yangjun/SwarmBalance/pull/7) |
| `p2-2-flight-energy-gate-v1` | `97200d2786a5fc775a8e6ea4ca5f95f90b5bcefb` | [#9](https://github.com/159357yangjun/SwarmBalance/pull/9) |
| `p2-4a-recovery-state-contract-v1` | `7ca10647201432062fbfd366fccba48027dbdd24` | [#14](https://github.com/159357yangjun/SwarmBalance/pull/14) |
| `p2-4b-b1-energy-quote-v1` | `fd8a001b09cb85b6875426d0e30532ee6e6831ac` | [#15](https://github.com/159357yangjun/SwarmBalance/pull/15) |
| `p2-4b-b2-station-reachability-v1` | `1601a36e7fb560b7126d13133d820a7bb4c60fe6` | [#16](https://github.com/159357yangjun/SwarmBalance/pull/16) |
| `p2-4b-b3-planned-station-quote-v1` | `b10b49e5e69a2d2b9986e20bf8b8b853460ec4f0` | [#17](https://github.com/159357yangjun/SwarmBalance/pull/17) |
| `p2-4b-b3b-planned-charge-route-v1` | `25a77553c710c06cc105986f140d66ba5c5c6c6d` | [#18](https://github.com/159357yangjun/SwarmBalance/pull/18) |
| `p2-4b-b3c-station-identity-v1` | `fca9ebfeb2413d8b396f20c10c98ddd50d2fcd47` | [#19](https://github.com/159357yangjun/SwarmBalance/pull/19) |
| `p2-4b-b4-auto-planned-nest-red-v1` | `e669075e120d3e646ec7f0623346608736f26966` | [#20](https://github.com/159357yangjun/SwarmBalance/pull/20) |
| `p2-4b-b4b-auto-target-closure-red-v1` | `69ea639f12a89141adc881ae614e511a72ede7d4` | [#23](https://github.com/159357yangjun/SwarmBalance/pull/23) |
| `p2-4b-b4c-held-route-requote-v1` | `42cf220143caff5fe12e91c0731279ed4486272e` | [#24](https://github.com/159357yangjun/SwarmBalance/pull/24) |
| `p2-4b-b4d-inflight-wind-energy-red-v1` | `47e64cac22dc5d1476f52a47b3ffd4f3d5ef9002` | [#25](https://github.com/159357yangjun/SwarmBalance/pull/25) |
| `p2-4b-b4e-end-to-end-conservation-red-v1` | `cea965f9b66e26473d4d1190a3f70c6cc8b7c61f` | [#26](https://github.com/159357yangjun/SwarmBalance/pull/26) |
| `p2-4b-b5a-cargo-custody-red-v1` | `ba3eac83151928a080d6c2abac40bdc4b245c704` | [#27](https://github.com/159357yangjun/SwarmBalance/pull/27) |
| `p2-4b-b5b-external-custody-handoff-red-v1` | `ac3660154e4729f9a56561ca312dc0cd94846f8b` | [#28](https://github.com/159357yangjun/SwarmBalance/pull/28) |
| `p2-4b-b5c-mixed-chain-custody-red-v1` | `4f5fc4639fe4b45296b6720454e5d946249bdcc1` | [#29](https://github.com/159357yangjun/SwarmBalance/pull/29) |
| `p2-4b-b5d-custody-journal-red-v1` | `907735e82591fff60840e21a7dcafb2a861ece71` | [#31](https://github.com/159357yangjun/SwarmBalance/pull/31) |
| `p2-4b-b5e-transactional-custody-red-v1` | `d32f11137f26c18e3c7f4e0a5ee925cd7d561fe3` | [#33](https://github.com/159357yangjun/SwarmBalance/pull/33) |
| `p2-4b-b5f-sqlite-queue-reconcile-red-v1` | `628f148e54fa3530e07c84e685f6ba4d7f27eece` | [#34](https://github.com/159357yangjun/SwarmBalance/pull/34) |
| `p2-4b-b5g-serialized-custody-reconcile-red-v1` | `121d94ab208869e417a89b2844563a26b8e7e101` | [#35](https://github.com/159357yangjun/SwarmBalance/pull/35) |

## B. MVP 另线成果（仅后端准备集成）（3 条）

| 分支（固定来源） | Head SHA | GitHub PR |
|---|---|---|
| `mvp01-backend` | `91af9c75492ee88fc2390a12bcefb8d4589d49ec` | [#62](https://github.com/159357yangjun/SwarmBalance/pull/62) |
| `mvp01-integration` | `674b6a548d97915ef94fc5bd0bc1a774a5d66902` | [#64](https://github.com/159357yangjun/SwarmBalance/pull/64) |
| `mvp01-workbench` | `674b6a548d97915ef94fc5bd0bc1a774a5d66902` | [#63](https://github.com/159357yangjun/SwarmBalance/pull/63) |

## C. P1/P2 分叉实验（保留证据，互斥实现未合）（9 条）

| 分支（固定来源） | Head SHA | GitHub PR |
|---|---|---|
| `p1-5-evidence-freeze-v1` | `1a47f07cc83243e6a345b9857c8cff156aeed73d` | [#8](https://github.com/159357yangjun/SwarmBalance/pull/8) |
| `p2-2-g2-root-cause-diagnostic-v1` | `3749cc0d70fbf22c2a39cba540b5f4f4d4534010` | [#13](https://github.com/159357yangjun/SwarmBalance/pull/13) |
| `p2-3-flight-feasibility-impact-v1` | `a2be17f061b01a55038eb91d95aea6ab270462f9` | [#10](https://github.com/159357yangjun/SwarmBalance/pull/10) |
| `p2-3b-forced-depletion-v1` | `5b023f72fc24231ce7c9e0b7a019f0fc101cbba9` | [#11](https://github.com/159357yangjun/SwarmBalance/pull/11) |
| `p2-3b-low-battery-trigger-v1` | `1d9246308086cbbea5c7fb49e50a6ea0bdd818e0` | [#12](https://github.com/159357yangjun/SwarmBalance/pull/12) |
| `p2-4b-b4b-auto-station-identity-v1` | `8c382fbf3b5fb7991f52dc21ab764a3dcc3f365b` | [#21](https://github.com/159357yangjun/SwarmBalance/pull/21) |
| `p2-4b-b4c-midflight-wind-guard-v1` | `6cc0631568c0550b7a3529215a194c24683dbea8` | [#22](https://github.com/159357yangjun/SwarmBalance/pull/22) |
| `p2-4b-b5d-durable-custody-journal-red-v1` | `d2da169e162c6f462ed2ebbb81a03ba91de0e818` | [#30](https://github.com/159357yangjun/SwarmBalance/pull/30) |
| `p2-4b-b5e-journaled-handoff-red-v1` | `eec90a621865669185d79488dff75e12b02f9a70` | [#32](https://github.com/159357yangjun/SwarmBalance/pull/32) |

## D. ARCH/CONTRACT 设计草案（非运行实现）（15 条）

| 分支（固定来源） | Head SHA | GitHub PR |
|---|---|---|
| `platform/arch-01-world` | `b5f05a70a3306f1799fcae2c3f342f3ed9ee0048` | [#46](https://github.com/159357yangjun/SwarmBalance/pull/46) |
| `platform/arch-02-harness` | `d155621aca66e3a80c388718093a452d17d71e10` | [#49](https://github.com/159357yangjun/SwarmBalance/pull/49) |
| `platform/arch-03-components` | `68382c649393057ffbf5a14508ab1ff72d575b09` | [#47](https://github.com/159357yangjun/SwarmBalance/pull/47) |
| `platform/arch-04-migration` | `c4c0c67111ead435062650c1ed776547c477e3e3` | [#50](https://github.com/159357yangjun/SwarmBalance/pull/50) |
| `platform/arch-05-r2-review` | `99bd0eb6b910d691d6d7776da0a5fd3f973f2997` | [#54](https://github.com/159357yangjun/SwarmBalance/pull/54) |
| `platform/arch-05-r3-contract-review` | `e76eb483d5760d99673774d48dc699f6a833ad7f` | [#59](https://github.com/159357yangjun/SwarmBalance/pull/59) |
| `platform/arch-05-review` | `4f7ccc1ffb37a6101169e7e6410cc78781abb527` | [#48](https://github.com/159357yangjun/SwarmBalance/pull/48) |
| `platform/arch-06-freeze-decision` | `6e7b69dc70c56a8e13f5cf7de750ad3c59068dcc` | [#61](https://github.com/159357yangjun/SwarmBalance/pull/61) |
| `platform/arch-exp-01-experiments` | `a966567b1a2a033f477c2847073cc11777a3afd2` | [#52](https://github.com/159357yangjun/SwarmBalance/pull/52) |
| `platform/arch-vve-01-credibility` | `9e9d8918c1e6989568e84c3f0d020fdffb0373de` | [#53](https://github.com/159357yangjun/SwarmBalance/pull/53) |
| `platform/contract-01-state-events` | `d7ff7a3b1c440f18f72fed326c54fe6594923375` | [#58](https://github.com/159357yangjun/SwarmBalance/pull/58) |
| `platform/contract-02-component-runtime` | `3c3d9caa20f60632661664497d8cb418fee5dbf1` | [#55](https://github.com/159357yangjun/SwarmBalance/pull/55) |
| `platform/contract-03-experiment-rng` | `6bdbe78f0da9294bdb1ac1c2590f5f2688d5bf01` | [#56](https://github.com/159357yangjun/SwarmBalance/pull/56) |
| `platform/contract-04-results-evidence` | `5c3bbadd60f39fc938703874c17dda07da216d42` | [#57](https://github.com/159357yangjun/SwarmBalance/pull/57) |
| `platform/contract-05-implementation-gates` | `abc93227b9e3160da1023d6c582e7a93ff9094b5` | [#60](https://github.com/159357yangjun/SwarmBalance/pull/60) |

## E. TaskUI 工具及审计（4 条）

| 分支（固定来源） | Head SHA | GitHub PR |
|---|---|---|
| `ui/taskui-00-audit` | `a0983f62013335ad6f96ed4e88a68ea8021b7b1b` | [#43](https://github.com/159357yangjun/SwarmBalance/pull/43) |
| `ui/taskui-01-rules` | `874ac7096595c3ba5b80da530373c6ef0593488c` | [#42](https://github.com/159357yangjun/SwarmBalance/pull/42) |
| `ui/taskui-02-requirements` | `7636e09f8e5f2cb46cf9360a6be722ad269f8fc1` | [#44](https://github.com/159357yangjun/SwarmBalance/pull/44) |
| `ui/taskui-b01-cross-review` | `298ec05be0bf114ea78e8184713231cbc066f697` | [#45](https://github.com/159357yangjun/SwarmBalance/pull/45) |

## F. 多智能体管理规范（1 条）

| 分支（固定来源） | Head SHA | GitHub PR |
|---|---|---|
| `governance/multi-agent-protocol-v1` | `f2df96bc609ee1e430ea6eff2456c4577347c300` | [#51](https://github.com/159357yangjun/SwarmBalance/pull/51) |

## G. 其他研究/审计分支（来源部分提取）（4 条）

| 分支（固定来源） | Head SHA | GitHub PR |
|---|---|---|
| `audit/l0-core-logic-readonly-20261012` | `ff7e03b8cb7a247b2731f86e42e8541ae1deece1` | [#40](https://github.com/159357yangjun/SwarmBalance/pull/40) |
| `docs/simulation-consistency-vv-guide-20261012` | `88be5e9fdffa507cf7e35b4e0c352a03d44267ee` | [#39](https://github.com/159357yangjun/SwarmBalance/pull/39) |
| `research/r1-energy-units-and-accounting-provenance-v1` | `2635141845efaf8e631bf54b16a63f5133982ae5` | [#37](https://github.com/159357yangjun/SwarmBalance/pull/37) |
| `research/r2-flight-data-source-feasibility-v1` | `f52111df94c5acd98dc8d9565c8a27bd1abfbd3c` | [#38](https://github.com/159357yangjun/SwarmBalance/pull/38) |
