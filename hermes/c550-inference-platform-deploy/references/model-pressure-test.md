═══ 模型推理压测结果

日期：2026-06-18
平台：C550 推理平台（10.140.158.130:8881）
每模型 10 个任务。

序列输入型（可直接测试）：

| 模型 | task_type | 提交 | 成功 | 失败 | 平均耗时 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| ankh3 | embed | 10 | 10 | 0 | 24s | — |
| deepfri | predict | 10 | 10 | 0 | 24s | — |
| esm2 | embed | 10 | 10 | 0 | 30s | 结果写入 AFS output_path |
| evo2 | forward | 10 | 10 | 0 | 43s | 第一轮氨基酸序列全挂，换 DNA 后通过 |
| proteinbert | embed | 10 | 10 | 0 | 31s | — |
| protrans | embed | 10 | 10 | 0 | 28s | — |

文件输入型（需 AFS 测试数据，本次未测）：

| 模型 | 需要 | 尝试次数 | 失败原因 |
| --- | --- | --- | --- |
| alphafold3 | input_json（含 MSA） | 9 | 缺 MSA 数据，无法用假序列绕过 |
| boltzgen | input_yaml | 11 | 当前版本不收 sequence |
| msatransformer | msa / msa_path | 11 | 当前版本不收 sequence |
| protenix | input_json | 11 | 当前版本不收 sequence |
| esmif1 | pdb_path | 0 | 无 PDB 测试文件 |
| mace | train_data_path | 0 | 训练模式 |
| mattersim | script + args | 0 | 无脚本 |
| mmseqs | db_path | 0 | 无数据库 |
| openfold | fasta_dir + alignments_dir | 0 | 无比对/模板数据 |
| promptir | image_path | 0 | 无图像文件 |
| proteinmpnn | input_quiver | 0 | 无 quiver 文件 |
| rfantibody | target_pdb + framework_pdb | 0 | 无 PDB 文件 |
| rfdiffusion | target_pdb + framework_pdb | 0 | 无 PDB 文件 |
| rosettafold | input_quiver | 0 | 无 quiver 文件 |

踩坑记录：

1. evo2 第一轮 10 个全挂
   原因：evoo2 是 DNA 模型，测试用了氨基酸序列 "MKFLIL..."
   错误："sequence must contain only A, T, C, G, N characters"
   修正：换成 DNA 序列 "ATGCGTACGTAGCTAG..." → 10/10 通过

2. alphafold3 三轮调试
   第一轮：字段不完整 → "Provide exactly one of input_dir or input_json"
   第二轮：缺 dialect/version → JSON 只含 name+sequences 被拒
   第三轮：缺 MSA → dialect+version+modelSeeds 都补齐后仍报 "missing unpaired MSA"
   结论：AF3 必须有真实 MSA 对齐数据，不能用假序列

3. boltzgen/msatransformer/protenix 历史任务用了 sequence
   AFS 上历史 taskmeta 显示这三个模型曾接受 sequence 输入
   当前版本已严格校验 input_yaml / msa_path / input_json，sequence 全被拒绝
   说明这些模型在新版本中收紧或修改了输入校验逻辑

测试输入参考：

  序列模型通用输入：
    {"task_type":"embed","inputs":{"sequence":"MKFLILFNILVCLAFSYAMGKSSSS","label":"test"}}

  evo2 DNA 输入：
    {"task_type":"forward","inputs":{"sequence":"ATGCGTACGTAGCTAGCTAGCTAGCTAGCTAGCTAGC"}}

  AF3 最简输入（还缺 MSA，会失败）：
    {
      "name":"test",
      "dialect":"alphafold3",
      "version":1,
      "modelSeeds":[42],
      "sequences":[{"protein":{"id":"A","sequence":"MKFLILFNILVC"}}]
    }