import ast
source_code = "x = 1 + 2"
tree = ast.parse(source_code)
print("=== AST 树桩结构 ===")
print(ast.dump(tree, indent=4))