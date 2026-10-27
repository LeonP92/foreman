from foreman import cli
from foreman.cli import main


def test_unknown_command_exits_1(capsys):
    assert main(["nope"]) == 1
    assert capsys.readouterr().err


def test_no_args_prints_usage_and_returns_1(capsys):
    assert main([]) == 1
    assert "usage" in capsys.readouterr().out.lower()


def test_commands_is_tuple():
    assert isinstance(cli.COMMANDS, tuple)
