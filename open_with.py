import sublime
import sublime_plugin
import os
import sys
import subprocess
from functools import partial
from pprint import pprint

SETTINGS_FILE = 'Default.sublime-settings'
SETTINGS_KEY = 'open_with'


class OpenWithCommand(sublime_plugin.WindowCommand):

    def cursor_position(self, view):
        return view.rowcol(view.sel()[0].begin())

    def activate(self, app):
        cmd = ['osascript', '-e',
               'tell application "{name}" to activate']
        self._run(cmd, app)

    def description(self):
        return 'Open file with application/editor.'

    def get_apps(self):
        return self.window.active_view().settings().get(SETTINGS_KEY, self.get_default_settings())

    @staticmethod
    def get_default_settings():
        return sublime.load_settings(SETTINGS_FILE).get(SETTINGS_KEY, [])

    def run(self, *args, **kwargs):
        apps = self.get_apps()
        select_app = partial(self.select_app, apps)
        if 'name' and ' command' in kwargs:
            self.prepare_command(kwargs)
        elif 'name' in kwargs:
            select_app(kwargs['name'])
        else:
            app_names = [app['name'] for app in apps]
            self.window.show_quick_panel(app_names, select_app)

    def select_app(self, apps, app_name):
        for i, app in enumerate(apps):
            if app_name == i or app_name == app['name']:
                self.prepare_command(app)

    def find_sublime_project_root(self, path):
        for file in os.listdir(path):
            if file.endswith('.sublime-project'):
                return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        return self.find_sublime_project_root(parent)

    def find_package_root(self, path):
        if os.path.exists(os.path.join(path, 'package.json')):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        return self.find_package_root(parent)

    def find_git_root(self, path):
        if os.path.exists(os.path.join(path, '.git')):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        return self.find_git_root(parent)

    def prepare_command(self, app):
        view = self.window.active_view()
        line, column = self.cursor_position(view)
        self.activate(app)
        filename = view.file_name()

        debug = app.get('debug', False)
        command_str = ''.join(app.get('command'))
        disabled_fallbacks = app.get('disabled_fallbacks', [])
        fallback_to_any_project = 'any_project' not in disabled_fallbacks
        fallback_to_package = 'package' not in disabled_fallbacks
        fallback_to_git = 'git' not in disabled_fallbacks

        requires_project = '{project}' in command_str
        requires_any_project = '{any_project}' in command_str or fallback_to_any_project
        requires_package = '{package}' in command_str or fallback_to_package
        requires_git = '{git}' in command_str or fallback_to_git

        project_dir = ''
        any_project_dir = self.find_sublime_project_root(os.path.dirname(filename)) if fallback_to_any_project else ''
        package_dir = self.find_package_root(os.path.dirname(filename)) if requires_package else ''
        git_dir = self.find_git_root(os.path.dirname(filename)) if requires_git else ''

        if requires_project:
            try:
                project_file = self.window.project_file_name()
                project_dir = os.path.dirname(project_file)

            except Exception as e:
                if not project_dir and fallback_to_any_project and any_project_dir:
                    if debug: print("[Open with...] fallback: any_project used", any_project_dir)
                    project_dir = any_project_dir

                if not project_dir and fallback_to_package and package_dir:
                    if debug: print("[Open with...] fallback: package used", package_dir)
                    project_dir = package_dir

                if not project_dir and fallback_to_git and git_dir:
                    if debug: print("[Open with...] fallback: git used", git_dir)
                    project_dir = git_dir

                if not project_dir:
                    sublime.error_message("Could not find your\n.sublime-project file!\n\n⚠️\n\nPlease open a project first to enable the {project} variable.")
                    print("[Open with...] error:", e)
                    return

        variables = {
            'line': line + 1,
            'column': column + 1,
            'filename': filename,
            'directory': os.path.dirname(filename),
            'project': project_dir,
            'any_project': any_project_dir,
            'package': package_dir,
            'git': git_dir
        }

        if debug:
            print("[Open with...] resolved variables:")
            pprint(variables)

        self._run(app.get('command'), variables)

    @staticmethod
    def _template(cmd, variables):
        return map(lambda s: s.format(**variables), cmd)

    def _run(self, cmd, variables):
        proc_env = os.environ.copy()
        encoding = sys.getfilesystemencoding()
        for k, v in proc_env.items():
            proc_env[k] = os.path.expandvars(v).encode(encoding)

        subprocess.Popen(self._template(cmd, variables), env=proc_env)
