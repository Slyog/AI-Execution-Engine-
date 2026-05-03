from unittest.mock import patch

from backend.docker_runner import DockerRunner


def test_linux_default_uses_unix_socket() -> None:
    with patch("backend.docker_runner.sys.platform", "linux"), patch.dict("os.environ", {}, clear=True):
        runner = DockerRunner()

    assert runner.docker_host == "unix:///var/run/docker.sock"
    assert runner.docker_host_source == "linux-default"


def test_linux_ignores_windows_npipe_docker_host() -> None:
    with (
        patch("backend.docker_runner.sys.platform", "linux"),
        patch.dict("os.environ", {"DOCKER_HOST": "npipe:////./pipe/dockerDesktopLinuxEngine"}, clear=True),
    ):
        runner = DockerRunner()

    assert runner.docker_host == "unix:///var/run/docker.sock"
    assert runner.docker_host_source == "linux-default-ignored-npipe-docker-host"
    assert runner._docker_environment()["DOCKER_HOST"] == "unix:///var/run/docker.sock"


def test_explicit_non_npipe_docker_host_is_respected() -> None:
    with (
        patch("backend.docker_runner.sys.platform", "linux"),
        patch.dict("os.environ", {"DOCKER_HOST": "tcp://docker:2375"}, clear=True),
    ):
        runner = DockerRunner()

    assert runner.docker_host == "tcp://docker:2375"
    assert runner.docker_host_source == "DOCKER_HOST"


def test_network_enabled_run_adds_host_gateway_mapping() -> None:
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b"ok\n", b""

        def poll(self):
            return 0

    captured = {}

    def fake_popen(command, stdout, stderr, env):
        captured["command"] = command
        captured["env"] = env
        return FakeProcess()

    with (
        patch("backend.docker_runner.sys.platform", "linux"),
        patch.dict("os.environ", {}, clear=True),
        patch("backend.docker_runner.subprocess.Popen", fake_popen),
    ):
        result = DockerRunner(network_disabled=True).run_python("print('ok')", allow_network=True)

    assert result["stdout"] == "ok\n"
    assert "--network" not in captured["command"]
    assert "--add-host" in captured["command"]
    host_index = captured["command"].index("--add-host")
    assert captured["command"][host_index + 1] == "host.docker.internal:host-gateway"
    assert DockerRunner()._command_has_host_gateway(captured["command"]) is True
    assert captured["env"]["DOCKER_HOST"] == "unix:///var/run/docker.sock"


def test_network_disabled_run_keeps_network_none_without_host_mapping() -> None:
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return b"ok\n", b""

        def poll(self):
            return 0

    captured = {}

    def fake_popen(command, stdout, stderr, env):
        captured["command"] = command
        return FakeProcess()

    with (
        patch("backend.docker_runner.sys.platform", "linux"),
        patch.dict("os.environ", {}, clear=True),
        patch("backend.docker_runner.subprocess.Popen", fake_popen),
    ):
        DockerRunner(network_disabled=True).run_python("print('ok')", allow_network=False)

    assert "--network" in captured["command"]
    network_index = captured["command"].index("--network")
    assert captured["command"][network_index + 1] == "none"
    assert "--add-host" not in captured["command"]


if __name__ == "__main__":
    test_linux_default_uses_unix_socket()
    test_linux_ignores_windows_npipe_docker_host()
    test_explicit_non_npipe_docker_host_is_respected()
    test_network_enabled_run_adds_host_gateway_mapping()
    test_network_disabled_run_keeps_network_none_without_host_mapping()
    print("docker host selection tests passed")
