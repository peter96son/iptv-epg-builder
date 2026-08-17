"""
Research helper placeholder.

The production builder never invents EPG mappings. Future tooling here can:
1. read output/unmatched.csv;
2. compare normalized names against downloaded XMLTV indexes;
3. emit *suggestions* with confidence scores;
4. require manual approval before adding a row to data/aliases.csv.

This separation keeps automated research from silently corrupting the live EPG.
"""
