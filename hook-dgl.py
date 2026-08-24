from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules, collect_data_files

binaries = collect_dynamic_libs('dgl')
datas = collect_data_files('dgl')
hiddenimports = collect_submodules('dgl')