# 派生作品说明 / Derivative-work notice — `c_0120.model3.json`

本文件记录对模型元数据的一次**改编（派生作品）**，按 **CC BY-NC-SA 4.0** 的要求留存。

- **日期 / date**：2026-09-30
- **处置人 / modified by**：`pet-integrate`（DSH usage widget 项目的桌宠整合负责项 task-7），
  依据用户明确批准（个人 / 给朋友的小范围自用）。
- **改的文件 / file modified**：`pet/model/c_0120.model3.json`
  （原文件备份为 `pet/model/c_0120.model3.json.bak-task7`）
- **改了什么 / what changed**（**只加声明，不动任何美术文件**）：
  1. 在 `FileReferences` 里**新增 `Expressions` 数组（44 条）**，把仓库里本来就有的
     44 个 `pet/model/expressions/*.exp3.json` 逐个声明出来（`Name` 用英文短名，
     `File` 指向原中文文件名）。缺少这段声明时，运行时的
     `expressionManager` 根本不存在——这是表情一直用不了的**唯一**原因。
  2. 把 `Groups[LipSync].Ids` 由 `[]` 改成 `["ParamMouthOpenY"]`，让说话时口型能动
     （该参数本来就存在于 `c_0120.cdi3.json` 与 `c_0120.moc3`，属纯声明）。
- **没有动 / untouched**：`c_0120.moc3`、全部贴图、全部 `.exp3.json`、全部
  `.motion3.json`、`c_0120.physics3.json`、`c_0120.cdi3.json`。
- **上游 / upstream**：模型素材来自 `Andersen216/dsh-whale-girl-live2d`；
  44 条表情声明的写法参照 `A8Chann/dsh-pet-live2d` 的 `pets/ds-whale-girl/c_0120.model3.json`。
  版权归 **上善无形 / ZipZipPipe / 氵六青**（见 `AUTHORS.md` / `PROVENANCE.md`）。

## 授权条件（照抄 CC BY-NC-SA 4.0）

这份 `c_0120.model3.json` 作为**派生作品**，与上游素材同协议：

1. **署名**：必须保留上述三位作者与素材来源的署名。
2. **非商业性使用**：不得用于商业目的（上游本身也是非商业项目）。
3. **相同方式共享**：对外分发时必须继续以 **CC BY-NC-SA 4.0** 发布。
4. **注明修改**：必须说明修改内容（即上面两条：补表情声明、补口型参数）。

**个人 / 小范围自用无需额外手续**；一旦对外分发，以上四条缺一不可。
本仓库其余代码的 MIT 许可**不覆盖**这份模型素材——不能只挂 MIT。

## 实测记录（这份派生文件确实生效）

生产页面 + 生产模型，`?selftest=1`，帧内取样、每个表情连续推进 1.6 s：

```
expressionManager        DEFINED
definitions              44
model.expression(name)   accepted 44/44
in-frame fingerprint     changed 44/44
```

原始报告：`pet/host/task7-expression-selftest.json`；规格与坑位：
`pet/REACTIONS-SPEC.md` §0、§6、§10、§12.4。
