#!/usr/bin/env python3
# 标准多语言 bundle 组装器（swe-multilang-production 参考实现）
# 输入: <lang> <id> <repo_dir> <gold_diff> <test_patch> <test_cmd> "<note>"
# 产出: <交付根>/bundles/<lang>/<id>/ 标准十文件结构
# 完整版见 180.184.86.2:/data/huron/swe/work_hermes_test_20260917/assemble_bundle.py
#
# 核心逻辑要点：
# 1. repo.tar.gz: cd repo_dir && tar czf out/repo.tar.gz --exclude=.git --exclude=node_modules \
#      --exclude=vendor --exclude=target --exclude=obj --exclude=.phpunit.result.cache .
#    （依赖另放 deps，保持源码快照干净）
# 2. deps: node_modules/vendor 打 tar.gz（run 时解压回 testbed）；csharp 打 .nuget 缓存
#    （run 时解压到 $WORK/nuget 并 export NUGET_PACKAGES）
# 3. problem_statement: 单遍扫原始轨迹 jsonl，从 messages[1] 的
#    <issue_description>...</issue_description> 正则提取
# 4. metadata.json 必含 source_archive_sha256 = sha256(repo.tar.gz)
# 5. run_mounted_eval.sh 模板：
#      tar 解压 repo → 恢复 deps → (git apply || patch -p1 --fuzz=3) test_patch
#      → gold 模式再 apply gold_patch → CI=1 <test_cmd>; rc=$?
#      → echo OPENSWE_EXIT_CODE=$rc; exit 0
#    前置失败路径分别 echo OPENSWE_EXIT_CODE=2/3/4 后 exit 0
# 6. run_redgreen.sh 模板：双模式循环，case "$mode:$marker" 判定
#      testonly:OPENSWE_EXIT_CODE=0|testonly:  → fail
#      gold:OPENSWE_EXIT_CODE=0                → pass
# 7. IMAGE 固定为当批基座镜像 swe-python-conda-runner:base-multilang-<date>
# 8. new-file test_patch 生成（make_newfile_diff.py）:
#      diff --git a/<rel> b/<rel> / new file mode 100644 / index 0000000..1111111 /
#      --- /dev/null / +++ b/<rel> / @@ -0,0 +1,N @@ / +每行
# 9. diff -u 格式转 git 格式：重写前两行头为 diff --git a/<rel> b/<rel> + --- a/ + +++ b/
pass
