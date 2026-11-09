from foreman.cli import main


def test_unknown_command_exits_1(capsys):
    assert main(["nope"]) == 1
    assert capsys.readouterr().err


def test_no_args_is_one_line_error(capsys):
    assert main([]) == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.count("\n") == 1
