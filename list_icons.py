from qfluentwidgets import FluentIcon as FIF
icons = [a for a in dir(FIF) if not a.startswith("_")]
print("\n".join(sorted(icons)))
