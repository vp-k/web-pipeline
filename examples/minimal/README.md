# Minimal lifecycle

`sample_test.py` is a real passing unittest, not evidence of a human approval. In an adopted project, register `["python", "-m", "unittest", "sample_test.py"]` as an argv command for a non-protected task, populate its documents and acceptance mapping, run `prepare`, then run Baseline and Full through the CLI. The task may reach only the gate allowed by its tier; in standard policy an unprotected T1 task still needs a recorded local review (`review`) before DONE, and strict policy needs a signed independent review. No example key or approval is supplied.

```console
cd examples/minimal
python -m unittest sample_test.py -v
python run_pipeline.py --output C:/temp/web-pipeline-example-evidence
```

The lifecycle runner creates a temporary adopted project and Git history, configures one real unittest check, executes Baseline and Full, and stops at REVIEW. Omit `--output` for disposable evidence; the output directory must not already exist.
