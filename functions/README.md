# functions/

Development working copies of the Sinas function handlers. Each file defines:

```python
def handler(input_data, context):
    ...
```

**Important runtime note.** Sinas function bodies run in an isolated sandbox and
can only use **admin-approved** pip packages (`spec.dependencies` in
`sinas-package.yaml`). They cannot import this repo's `src/clip2trace` package at
runtime. So the *deployable* version of each function is the **inline `code:`
block in `sinas-package.yaml`**, which is self-contained.

These files import `clip2trace.*` for readability and local testing. Before
deploying, either (a) keep the YAML inline blocks as the source of truth, or
(b) publish `clip2trace` as an approved dependency. See issue "Add base function
schemas and stubs" and docs/architecture.md.
