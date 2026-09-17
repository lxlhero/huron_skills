#!/usr/bin/env python3
"""Run the bundle-local mounted validator without shared environment fallback."""
import argparse, pathlib, subprocess, tempfile

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=pathlib.Path,required=True)
    p.add_argument('--validator',type=pathlib.Path,required=True)
    p.add_argument('--output',type=pathlib.Path,required=True)
    p.add_argument('--timeout-seconds',type=int,default=900)
    a=p.parse_args();bundle=a.bundle.resolve();output=a.output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='swe-image-canary-') as work:
        cmd=['python3',str(a.validator.resolve()),'one','--bundle-root',str(bundle.parent),'--task-id',bundle.name,'--mode','redgreen','--require-bundle-local-env','--no-regenerate-scripts','--network','none','--run-root',work,'--results-dir',str(output.parent),'--output',str(output),'--timeout-seconds',str(a.timeout_seconds)]
        raise SystemExit(subprocess.call(cmd))
if __name__=='__main__':main()
