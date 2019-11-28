import click
import os
import os.path
import sys
from paco.commands.helpers import pass_paco_context, aim_home_option, init_aim_home_option
from cookiecutter.main import cookiecutter
from jinja2.ext import Extension


def env_override(value, key):
    env_value = os.getenv(key, value)
    if env_value:
        return env_value
    else:
        return value

class EnvOverrideExtension(Extension):
    def __init__(self, environment):
        super(EnvOverrideExtension, self).__init__(environment)
        environment.filters['env_override'] = env_override

def init_args(func):
    func = click.argument("ACTION", required=True, type=click.STRING)(func)
    return func

@click.group(name="init")
@click.pass_context
def init_group(paco_ctx):
    """
    Commands for initializing Paco projects.
    """
    pass

@init_group.command(name="project")
@click.argument("project-name")
@click.pass_context
def init_project(ctx, project_name):
    """
    Creates a new directory with a tempalted Paco project in it.
    """
    paco_ctx = ctx.obj
    paco_ctx.command = 'init project'

    # As we are initializing the project, laod_project needs to behave differently
    paco_ctx.home = os.getcwd() + os.sep + project_name
    paco_ctx.load_project(project_init=True)
    ctl_project = paco_ctx.get_controller('project')
    ctl_project.init_project()

@init_group.command(name="credentials")
@aim_home_option
@click.pass_context
def init_credentials(ctx, home='.'):
    """
    Initializes the .credentials file for an AIM project.
    """
    paco_ctx = ctx.obj
    paco_ctx.command = 'init credentials'
    init_aim_home_option(paco_ctx, home)
    paco_ctx.load_project(project_init=True)
    ctl_project = paco_ctx.get_controller('project')
    ctl_project.init_credentials()

@init_group.command(name="accounts")
@aim_home_option
@click.pass_context
def init_accounts(ctx, home='.'):
    """
    Initializes the accounts for an Paco project.
    """
    paco_ctx = ctx.obj
    paco_ctx.command = 'init accounts'
    init_aim_home_option(paco_ctx, home)
    paco_ctx.load_project()
    ctl_project = paco_ctx.get_controller('project')
    ctl_project.init_accounts()

@init_group.command(name="netenv")
@aim_home_option
@click.pass_context
def init_netenv(ctx, home='.'):
    """
    Initializes a netenv resource for an Paco project.
    """
    paco_ctx = ctx.obj
    paco_ctx.command = 'init netenv'
    init_aim_home_option(paco_ctx, home)
    paco_ctx.load_project()
    ctl_project = paco_ctx.get_controller('project')
    # ToDo: FixMe! pass proper NetEnv info to init_command ...
    ctl_project.init_command()