"""
Tests for Sanitizer — PC command validation and tool gating.
"""
import pytest
from sanitizer import Sanitizer


class TestSanitizerPCToolGating:
    """Test that PC tools are allowed/blocked correctly."""

    def test_get_pc_status_allowed(self, sanitizer):
        result = sanitizer.validate_tool_call("get_pc_status", {})
        assert result["allowed"] is True

    def test_control_browser_allowed(self, sanitizer):
        result = sanitizer.validate_tool_call("control_browser", {"action": "get_url"})
        assert result["allowed"] is True

    def test_send_pc_notification_allowed(self, sanitizer):
        result = sanitizer.validate_tool_call("send_pc_notification", {
            "title": "Test", "body": "Hello",
        })
        assert result["allowed"] is True

    def test_unknown_tool_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("nonexistent_tool", {})
        assert result["allowed"] is False


class TestSanitizerPCCommandValidation:
    """Test dangerous command blocklist for run_pc_command."""

    def test_safe_command_allowed(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "ls -la /home",
        })
        assert result["allowed"] is True

    def test_uname_allowed(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "uname -a",
        })
        assert result["allowed"] is True

    def test_python_allowed(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "python3 -c 'print(1+1)'",
        })
        assert result["allowed"] is True

    def test_empty_command_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {"command": ""})
        assert result["allowed"] is False

    def test_rm_rf_root_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "rm -rf /",
        })
        assert result["allowed"] is False

    def test_rm_rf_home_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "rm -rf /home/user",
        })
        assert result["allowed"] is False

    def test_rm_f_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "rm -f /etc/passwd",
        })
        assert result["allowed"] is False

    def test_rm_r_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "rm -r /var/log",
        })
        assert result["allowed"] is False

    def test_mkfs_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "mkfs.ext4 /dev/sda1",
        })
        assert result["allowed"] is False

    def test_shutdown_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "shutdown -h now",
        })
        assert result["allowed"] is False

    def test_reboot_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "reboot",
        })
        assert result["allowed"] is False

    def test_poweroff_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "poweroff",
        })
        assert result["allowed"] is False

    def test_dd_to_device_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "dd if=/dev/zero of=/dev/sda bs=1M",
        })
        assert result["allowed"] is False

    def test_systemctl_halt_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "systemctl poweroff",
        })
        assert result["allowed"] is False

    def test_systemctl_reboot_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "systemctl reboot",
        })
        assert result["allowed"] is False

    def test_chmod_777_root_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "chmod -R 777 /",
        })
        assert result["allowed"] is False

    def test_safe_rm_in_subdirectory_allowed(self, sanitizer):
        """rm in a non-root directory should be allowed."""
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "rm /tmp/test.txt",
        })
        assert result["allowed"] is True

    def test_safe_systemctl_status_allowed(self, sanitizer):
        """systemctl status should be allowed (not halt/poweroff/reboot)."""
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "systemctl status nginx",
        })
        assert result["allowed"] is True

    def test_init_0_blocked(self, sanitizer):
        result = sanitizer.validate_tool_call("run_pc_command", {
            "command": "init 0",
        })
        assert result["allowed"] is False
