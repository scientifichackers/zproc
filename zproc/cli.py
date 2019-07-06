import os

import click
from decouple import AutoConfig

from zproc.server import tools


@click.group()
def cli():
    pass


tools.config = AutoConfig(search_path=os.getcwd())


@click.command("start-server")
@click.argument("server_address", required=False)
@click.option("--pid-file", "-p", type=click.Path())
def start_server(server_address, pid_file):
    proc, addr = tools.start_server(server_address=server_address, pid_file=pid_file)
    print(f"[ZProc] Server started @ {addr!r}")
    proc.join()


cli.add_command(start_server)
