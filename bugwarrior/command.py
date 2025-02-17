import functools
import os
import sys

from lockfile import LockTimeout
from lockfile.pidlockfile import PIDLockFile

import getpass
import click

from bugwarrior.config import get_keyring, get_config_path, load_config
from bugwarrior.collect import aggregate_issues, get_service
from bugwarrior.db import (
    get_defined_udas_as_strings,
    synchronize,
)

import logging
log = logging.getLogger(__name__)


# We overwrite 'list' further down.
lst = list


def _get_section_name(flavor):
    if flavor:
        return 'flavor.' + flavor
    return 'general'


def _try_load_config(main_section, interactive=False, quiet=False):
    try:
        return load_config(main_section, interactive, quiet)
    except OSError:
        # Our standard logging configuration depends on the bugwarrior
        # configuration file which just failed to load.
        logging.basicConfig()

        exc_info = sys.exc_info()
        log.critical("Could not load configuration. "
                     "Maybe you have not created a configuration file.",
                     exc_info=(exc_info[0], exc_info[1], None))
        sys.exit(1)


def _legacy_cli_deprecation_warning(subcommand_callback):
    @functools.wraps(subcommand_callback)
    @click.pass_context
    def wrapped_subcommand_callback(ctx, *args, **kwargs):
        if ctx.find_root().command_path != 'bugwarrior':
            old_command = ctx.command_path
            new_command = ctx.command_path.replace('-', ' ')
            log.warning(
                f'Deprecation Warning: `{old_command}` is deprecated and will '
                'be removed in a future version of bugwarrior. Please use '
                f'`{new_command}` instead.')
        return ctx.invoke(subcommand_callback, *args, **kwargs)
    return wrapped_subcommand_callback


class AliasedCli(click.Group):
    """
    Integrates subcommands into a top-level bugwarrior command.

    By implementing this as an alias, we can maintain backwards compatibility
    with the old cli api.
    """
    def list_commands(self, ctx):
        return ctx.command.commands.keys()

    def get_command(self, ctx, name):
        return ctx.command.commands[name]


@click.command(cls=AliasedCli)
@click.version_option()
def cli():
    pass


@cli.command()
@click.option('--dry-run', is_flag=True)
@click.option('--flavor', default=None, help='The flavor to use')
@click.option('--interactive', is_flag=True)
@click.option('--debug', is_flag=True,
              help='Do not use multiprocessing (which breaks pdb).')
@click.option('--quiet', is_flag=True, help='Set logging level to WARNING.')
@_legacy_cli_deprecation_warning
def pull(dry_run, flavor, interactive, debug, quiet):
    """ Pull down tasks from forges and add them to your taskwarrior tasks.

    Relies on configuration in bugwarriorrc
    """

    try:
        main_section = _get_section_name(flavor)
        config = _try_load_config(main_section, interactive, quiet)

        lockfile_path = os.path.join(
            config[main_section].data.path, 'bugwarrior.lockfile')
        lockfile = PIDLockFile(lockfile_path)
        lockfile.acquire(timeout=10)
        try:
            # Get all the issues.  This can take a while.
            issue_generator = aggregate_issues(config, main_section, debug)

            # Stuff them in the taskwarrior db as necessary
            synchronize(issue_generator, config, main_section, dry_run)
        finally:
            lockfile.release()
    except LockTimeout:
        log.critical(
            'Your taskrc repository is currently locked. '
            'Remove the file at %s if you are sure no other '
            'bugwarrior processes are currently running.' % (
                lockfile_path
            )
        )
        sys.exit(1)
    except RuntimeError as e:
        log.exception("Aborted (%s)" % e)
        sys.exit(1)


@cli.group()
@_legacy_cli_deprecation_warning
def vault():
    """ Password/keyring management for bugwarrior.

    If you use the keyring password oracle in your bugwarrior config, this tool
    can be used to manage your keyring.
    """
    pass


def targets():
    config = _try_load_config('general')
    for target in config['general'].targets:
        service_class = get_service(config[target].service)
        for value in [v for v in dict(config[target]).values()
                      if isinstance(v, str)]:
            if '@oracle:use_keyring' in value:
                yield service_class.get_keyring_service(config[target])


@vault.command()
def list():
    pws = lst(targets())
    print("%i @oracle:use_keyring passwords in bugwarriorrc" % len(pws))
    for section in pws:
        print("-", section)


@vault.command()
@click.argument('target')
@click.argument('username')
def clear(target, username):
    target_list = lst(targets())
    if target not in target_list:
        raise ValueError("%s must be one of %r" % (target, target_list))

    keyring = get_keyring()
    if keyring.get_password(target, username):
        keyring.delete_password(target, username)
        print("Password cleared for %s, %s" % (target, username))
    else:
        print("No password found for %s, %s" % (target, username))


@vault.command()
@click.argument('target')
@click.argument('username')
def set(target, username):
    target_list = lst(targets())
    if target not in target_list:
        log.warning("You must configure the password to '@oracle:use_keyring' "
                    "prior to setting the value.")
        raise ValueError("%s must be one of %r" % (target, target_list))

    keyring = get_keyring()
    keyring.set_password(target, username, getpass.getpass())
    print("Password set for %s, %s" % (target, username))


@cli.command()
@click.option('--flavor', default=None, help='The flavor to use')
@_legacy_cli_deprecation_warning
def uda(flavor):
    """
    List bugwarrior-managed uda's.

    Most services define a set of UDAs in which bugwarrior store extra information
    about the incoming ticket.  Usually, this includes things like the title
    of the ticket and its URL, but some services provide an extensive amount of
    metadata.  See each service's documentation for more information.

    For using this data in reports, it is recommended that you add these UDA
    definitions to your ``taskrc`` file. You can add the output of this command
    verbatim to your ``taskrc`` file if you would like Taskwarrior to know the
    human-readable name and data type for the defined UDAs.

    .. note::

       Not adding those lines to your ``taskrc`` file will have no negative
       effects aside from Taskwarrior not knowing the human-readable name for the
       field, but depending on what version of Taskwarrior you are using, it
       may prevent you from changing the values of those fields or using them
       in filter expressions.
    """
    main_section = _get_section_name(flavor)
    conf = _try_load_config(main_section)
    print("# Bugwarrior UDAs")
    for uda in get_defined_udas_as_strings(conf, main_section):
        print(uda)
    print("# END Bugwarrior UDAs")


@cli.command()
@click.argument('rcfile', required=False, default=get_config_path(),
                type=click.Path(exists=True))
def ini2toml(rcfile):
    """ Convert ini bugwarriorrc to toml and print result to stdout. """
    try:
        from ini2toml.api import Translator
    except ImportError:
        raise SystemExit(
            'Install extra dependencies to use this command:\n'
            '    pip install bugwarrior[ini2toml]')
    if os.path.splitext(rcfile)[-1] == '.toml':
        raise SystemExit(f'{rcfile} is already toml!')
    with open(rcfile, 'r') as f:
        bugwarriorrc = f.read()
    print(Translator().translate(bugwarriorrc, 'bugwarriorrc'))
