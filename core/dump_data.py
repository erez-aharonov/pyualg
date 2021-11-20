import inspect
import pandas as pd
import types
import re
import pickle
import nbformat as nbf
import os
import uuid
from typing import *
import sys


def take_it_offline(notebook_dir_path: Optional[str] = None):
    notebook_dir_path = _get_notebook_dir_path(notebook_dir_path)
    random_name = str(uuid.uuid4()).replace('-', '')
    pickle_file_name = random_name + '.pkl'
    pickle_path = os.path.join(notebook_dir_path, pickle_file_name)
    notebook_path = os.path.join(notebook_dir_path, random_name) + '.ipynb'

    stack = inspect.stack()
    stack_df = _make_stack_df(stack)
    stack_df.to_pickle(pickle_path)

    sys_path_list = sys.path

    notebook = _create_notebook_object(stack_df, sys_path_list, pickle_file_name)
    nbf.write(notebook, notebook_path)


def _create_notebook_object(stack_df, sys_path_list, pickle_file_name):
    notebook = nbf.v4.new_notebook()
    intro_markdown = nbf.v4.new_markdown_cell("# Generated by alkh")

    append_to_sys_path_str = "import sys\n"
    for path_to_append in sys_path_list[:-2]:
        append_to_sys_path_str += f"sys.path.append(\'{path_to_append}\')\n"
    append_to_sys_path_str += f"sys.path.append(\'{sys_path_list[-1]}\')"
    append_to_sys_path_cell = nbf.v4.new_code_cell(append_to_sys_path_str)

    import_packages_str = """import pandas as pd
import alkh"""
    import_packages = nbf.v4.new_code_cell(import_packages_str)

    read_pickle_and_display_text = f"""stack_df = pd.read_pickle('{pickle_file_name}')
stack_df[["file_path", "function", "lineno", "locals_names"]]"""
    read_pickle_and_display = nbf.v4.new_code_cell(read_pickle_and_display_text)
    stack_cells = []
    for index, _ in stack_df.iterrows():
        stack_cells.append(nbf.v4.new_code_cell(f"alkh.print_context(stack_df.loc[{index}, \'context\'])"))
        stack_cells.append(nbf.v4.new_code_cell(f"stack_df.loc[{index}, \'locals\']"))
    cells_list = [intro_markdown, append_to_sys_path_cell, import_packages, read_pickle_and_display] + stack_cells
    notebook['cells'] = cells_list
    return notebook


def _get_notebook_dir_path(notebook_dir_path: Optional[str]):
    if notebook_dir_path is None:
        notebook_dir_path = os.getenv('ALKH_NOTEBOOKS_PATH')
        if notebook_dir_path is None:
            message = 'notebook_dir_path is not provided and ALKH_NOTEBOOKS_PATH is not in environment variables'
            raise EnvironmentError(message)
    if not os.path.isdir(notebook_dir_path):
        raise OSError(f"{notebook_dir_path} does not exists")
    return notebook_dir_path


def _make_stack_df(stack):
    stack_tuples_list = [(frame.filename, frame.function, frame.lineno, frame) for frame in stack]
    raw_stack_df = pd.DataFrame(stack_tuples_list, columns=['file_path', 'function', 'lineno', 'frame'])
    relevant_stack_df = \
        raw_stack_df[~(raw_stack_df['file_path'].str.contains('ipython') |
                       raw_stack_df['file_path'].str.contains('pycharm') |
                       raw_stack_df['file_path'].str.contains('site') |
                       raw_stack_df['file_path'].str.contains('alkh/core/dump_data.py'))].copy()
    relevant_stack_df['locals'] = _get_data_frame_locals(relevant_stack_df)
    relevant_stack_df['locals_names'] = relevant_stack_df['locals'].apply(_get_keys)
    stack_df = relevant_stack_df[['file_path', 'function', 'lineno', 'locals_names', 'locals']].reset_index(drop=True)
    stack_df['context'] = stack_df.apply(_get_context_lines, axis=1)
    return stack_df


def _get_keys(a_dict: dict):
    return list(a_dict.keys())


def _get_data_frame_locals(df):
    def _get_relevant_locals(locals_dict):
        list_to_remove = [
            'self',
            '__name__',
            '__doc__',
            '__package__',
            '__loader__',
            '__spec__',
            '__file__',
            '__builtins__',
            '__builtin__',
            '_ih',
            '_oh',
            '_dh',
            'In',
            'Out',
            'get_ipython',
            'exit',
            'quit',
            '_',
            '__',
            '___',
            '_i',
            '_ii',
            '_iii']

        relevant_locals_dict = {}

        for key in locals_dict.keys():
            cond1 = not re.search('_i[0-9]+', key)
            cond2 = key not in list_to_remove
            cond3 = not isinstance(locals_dict[key], types.ModuleType)
            cond4 = not isinstance(locals_dict[key], types.FunctionType)
            cond5 = not isinstance(locals_dict[key], type)
            if cond1 and cond2 and cond3 and cond4 and cond5:
                try:
                    pickle.dumps(locals_dict[key])
                    relevant_locals_dict[key] = locals_dict[key]
                except (pickle.PickleError, TypeError):
                    pass

        return relevant_locals_dict

    def _get_frame_locals(a_frame):
        frame_locals = a_frame.frame.f_locals
        frame_locals_2 = _get_relevant_locals(frame_locals)
        return frame_locals_2

    locals_series = df['frame'].apply(_get_frame_locals)
    return locals_series


def _get_context_lines(a_series):
    file_path = a_series['file_path']
    lineno = a_series['lineno']

    with open(file_path, 'r') as a_file:
        lines = a_file.readlines()

    context_length = 2
    start_index = max(0, lineno - context_length - 1)
    end_index = min(lineno + context_length, len(lines))
    line_numbers_list = list(range(start_index, end_index))
    context_lines_list = lines[start_index: end_index]

    numbers_with_lines_list = _create_numbers_with_lines_list(context_lines_list, line_numbers_list)
    output = [file_path] + numbers_with_lines_list
    return output


def _create_numbers_with_lines_list(context_lines_list, line_numbers_list):
    numbers_with_lines_list = []
    for context_line, line_number in zip(context_lines_list, line_numbers_list):
        final_line = f"{line_number}: {context_line.rstrip()}"
        numbers_with_lines_list.append(final_line)
    return numbers_with_lines_list