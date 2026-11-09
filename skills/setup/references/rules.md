# Writing an import rule

A rule's `pattern` matches the statements that load another file when this one loads:
`require`, `require_relative`, `import`, `use`, `include` and the like.

Leave lazy-load directives out: Ruby's `autoload :Cart, "shop/cart"`, or any registration
that only names a file to load on first use. They point from an index file to everything
it could load, so matching them turns that index into a false hub and hides which files
really use each other. An index that only `autoload`s is treated as a re-export file and
never flagged as a hub.

Example (invented):

```toml
[graph.ruby]
extensions = [".rb"]
pattern = "^\\s*require(?:_relative)?\\s+['\"](.+?)['\"]"
resolve = ["{dir}/{1}.rb", "lib/{1}.rb"]
```
