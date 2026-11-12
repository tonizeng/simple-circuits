"""Reply to board-initiated enable requests. Firmware owns power and shutdown.

This module never emits power-on, power-off, current-limit, or reset commands.
A decision is valid only for the matching fresh request and topology revision.
"""
from dataclasses import dataclass, replace
import time
from circuit_safety import SafetyLimits, SafetyIssue, is_finite_number


@dataclass(frozen=True)
class PowerDecision:
    request_id: str
    topology_revision: int
    granted: bool
    issues: tuple
    max_voltage_v: float
    max_current_a: float


class PowerProtection:
    def __init__(self, limits=SafetyLimits(), clock=time.monotonic, timeout_s=1.0):
        if not is_finite_number(timeout_s) or timeout_s <= 0:
            raise ValueError('Telemetry timeout must be positive and finite.')
        self.limits = limits
        self.clock = clock
        self.timeout_s = timeout_s
        self.transport = None
        self.report = None
        self.topology_revision = None
        self.highest_revision = -1
        self.last_sample = None
        self.voltage_v = None
        self.current_a = None
        self.measurement_issue = None
        self.firmware_fault = None
        self.link_issue = None
        self.last_decision = None
        self.seen_requests = set()

    def attach_transport(self, sender):
        if not callable(sender):
            raise TypeError('Transport must accept a PowerDecision.')
        if self.transport is not None:
            raise RuntimeError('Disconnect the existing transport first.')
        self.transport = sender
        self.report = None
        self.topology_revision = None
        self.highest_revision = -1
        self.last_sample = None
        self.voltage_v = self.current_a = None
        self.measurement_issue = self.firmware_fault = self.link_issue = None
        self.last_decision = None
        self.seen_requests.clear()

    def disconnect(self):
        self.transport = None
        self.report = None
        self.topology_revision = None
        self.last_sample = None
        self.last_decision = None
        # Firmware must independently detect link loss and shut down if required.

    def update_report(self, report, topology_changed=True, revision=None):
        self.report = report
        if topology_changed:
            self.last_decision = None
            self.topology_revision = None
            if self.transport is not None and type(revision) is int and revision > self.highest_revision:
                self.highest_revision = revision
                self.topology_revision = revision
        # Measurement-only reassessment must not turn a library circuit into board data.

    @property
    def measurements_fresh(self):
        return self.last_sample is not None and 0 <= self.clock() - self.last_sample <= self.timeout_s

    @property
    def runtime_issues(self):
        issues = []
        if self.firmware_fault:
            issues.append(SafetyIssue('firmware_fault', self.firmware_fault))
        if self.measurement_issue:
            issues.append(self.measurement_issue)
        if self.link_issue:
            issues.append(SafetyIssue('response_failed', self.link_issue))
        if self.transport is not None and self.last_sample is not None and not self.measurements_fresh:
            issues.append(SafetyIssue('stale_telemetry', 'Supply measurements are out of date.', severity='warning'))
        return tuple(issues)

    def observe(self, voltage_v, current_a):
        if not all(is_finite_number(v) for v in (voltage_v, current_a)):
            self.last_sample = None
            self.measurement_issue = SafetyIssue('invalid_measurement', 'Invalid supply voltage or current measurement.')
            return False
        self.voltage_v, self.current_a = voltage_v, current_a
        self.last_sample = self.clock()
        self.measurement_issue = None
        if not 0 <= voltage_v <= self.limits.max_voltage_v:
            self.measurement_issue = SafetyIssue('measured_overvoltage',
                f'Measured voltage {voltage_v:g} V is outside 0–{self.limits.max_voltage_v:g} V.')
        elif abs(current_a) > self.limits.max_current_a:
            self.measurement_issue = SafetyIssue('measured_overcurrent',
                f'Measured current {abs(current_a):g} A exceeds {self.limits.max_current_a:g} A.')
        return self.measurement_issue is None

    def report_firmware_fault(self, message):
        if message is not None and (not isinstance(message, str) or not message.strip()):
            raise ValueError('Firmware fault must be a nonempty string, or None to report cleared.')
        self.firmware_fault = message

    def handle_enable_request(self, request_id, topology_revision):
        issues = list(self.report.issues) if self.report is not None else [
            SafetyIssue('no_validation', 'No validated board circuit is available.')]
        if self.transport is None:
            issues.append(SafetyIssue('not_connected', 'The firmware connection is not available.'))
        if not isinstance(request_id, str) or not request_id.strip():
            issues.append(SafetyIssue('invalid_request', 'Enable request ID is missing or invalid.'))
        elif request_id in self.seen_requests:
            issues.append(SafetyIssue('duplicate_request', 'This enable request has already been handled.'))
        elif len(self.seen_requests) >= 4096:
            issues.append(SafetyIssue('request_capacity', 'Reconnect before sending further enable requests.'))
        else:
            self.seen_requests.add(request_id)
        if (self.topology_revision is None or type(topology_revision) is not int
            or topology_revision != self.topology_revision):
            issues.append(SafetyIssue('topology_mismatch', 'The request does not match the latest validated board topology.'))
        if not self.measurements_fresh:
            issues.append(SafetyIssue('missing_telemetry', 'Fresh battery voltage and load-current readings are required.', severity='warning'))
        issues.extend(self.runtime_issues)
        decision = PowerDecision(request_id, topology_revision, not issues, tuple(issues),
                                 self.limits.max_voltage_v, self.limits.max_current_a)
        if self.transport is not None:
            try:
                self.transport(decision)
            except Exception:
                self.link_issue = 'Could not deliver the validation response to firmware.'
                decision = replace(decision, granted=False,
                    issues=decision.issues + (SafetyIssue('response_failed', self.link_issue),))
        self.last_decision = decision
        return decision
