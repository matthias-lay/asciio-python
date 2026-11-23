import os
import subprocess
import sys
from pathlib import Path

from asciio import storage

ROOT = Path(__file__).parents[1]


def make(prefix, *targets, destdir=None):
    args = [
        "make",
        *targets,
        f"PREFIX={prefix}",
        f"PYTHON={sys.executable}",
    ]
    if destdir is not None:
        args.append(f"DESTDIR={destdir}")
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)


def test_prefix_install_uses_its_own_code_and_selected_python_and_uninstalls(tmp_path):
    prefix = tmp_path / "prefix with spaces"
    result = make(prefix, "install")
    assert result.returncode == 0, result.stderr
    launcher = prefix / "bin" / "asciio-python"
    assert launcher.is_symlink()
    assert launcher.read_text().splitlines()[0] == "#!" + sys.executable
    script = tmp_path / "where.py"
    script.write_text("import asciio\neditor.add('text', str(asciio.__file__))\n")
    output = tmp_path / "where.pasciio"
    result = subprocess.run(
        [str(launcher), "run", str(script), "-o", str(output)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert storage.load(output).elements[0].text == str(
        prefix / "share" / "asciio-python" / "asciio" / "__init__.py"
    )
    converter = prefix / "bin" / "text_to_asciio"
    result = subprocess.run(
        [str(converter), "-o", str(output)],
        input="native install",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert storage.load(output).render() == "native install\n"
    # An executable replaced by the user must not be deleted on uninstall.
    unrelated = prefix / "bin" / "asciio"
    unrelated.unlink()
    unrelated.write_text("keep this command\n")
    result = make(prefix, "uninstall")
    assert result.returncode == 0, result.stderr
    assert unrelated.read_text() == "keep this command\n"
    assert not os.path.lexists(launcher)
    assert not (prefix / "share" / "asciio-python").exists()


def test_install_refuses_to_replace_unrelated_commands_before_copying_files(tmp_path):
    prefix = tmp_path / "prefix"
    executable = prefix / "bin" / "asciio"
    executable.parent.mkdir(parents=True)
    executable.write_text("existing Perl or other application")
    result = make(prefix, "install")
    assert result.returncode != 0
    assert "Refusing to overwrite" in result.stderr
    assert executable.read_text() == "existing Perl or other application"
    assert not (prefix / "share" / "asciio-python").exists()


def test_destdir_staging_keeps_relative_launchers_relocatable(tmp_path):
    result = make("/usr/local", "install", destdir=tmp_path)
    assert result.returncode == 0, result.stderr
    launcher = tmp_path / "usr" / "local" / "bin" / "asciio-python"
    result = subprocess.run(
        [str(launcher), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"
