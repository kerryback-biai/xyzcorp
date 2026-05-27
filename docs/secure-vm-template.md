# Secure VM Setup for AI Agent Data Analysis

## Purpose

Provide a locked-down environment where an AI coding agent (e.g., Claude Code) can access enterprise APIs and analyze company data without risk of data exfiltration to untrusted external sites.

## Architecture Overview

```
[Employee] --> [Remote Desktop / SSH] --> [Secured VM]
                                              |
                                    [Firewall / Proxy]
                                              |
                              +---------------+---------------+
                              |               |               |
                        [Anthropic API]  [Salesforce]   [Workday, etc.]
```

## 1. VM Configuration

| Component        | Recommendation                                      |
|------------------|-----------------------------------------------------|
| OS               | Ubuntu 22.04 LTS or company-standard Linux image    |
| Access method    | Remote desktop or SSH only (no local file transfer)  |
| Clipboard        | Disable copy/paste to local machine                  |
| Storage          | No USB or external drive mounting                    |
| Python           | 3.11+ with pandas, numpy, matplotlib, etc.           |
| Node.js          | 20 LTS (if generating documents)                     |
| Claude Code      | Latest version via npm                               |

## 2. Network Allowlist

Block all outbound traffic by default. Allow only these destinations:

| Destination              | Port | Purpose                  |
|--------------------------|------|--------------------------|
| api.anthropic.com        | 443  | Claude API               |
| login.salesforce.com     | 443  | Salesforce auth           |
| *.my.salesforce.com      | 443  | Salesforce data API       |
| *.workday.com            | 443  | Workday API               |
| *[add other APIs]*       | 443  | Other enterprise systems   |
| Internal network ranges  | *    | Company infrastructure     |

Example firewall rules (iptables):

```bash
# Default deny outbound
iptables -P OUTPUT DROP

# Allow loopback
iptables -A OUTPUT -o lo -j ACCEPT

# Allow established connections
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow DNS (internal DNS server)
iptables -A OUTPUT -d <DNS_SERVER_IP> -p udp --dport 53 -j ACCEPT

# Allow Anthropic API
iptables -A OUTPUT -d api.anthropic.com -p tcp --dport 443 -j ACCEPT

# Allow Salesforce
iptables -A OUTPUT -d login.salesforce.com -p tcp --dport 443 -j ACCEPT
iptables -A OUTPUT -d <salesforce_instance>.my.salesforce.com -p tcp --dport 443 -j ACCEPT

# Allow Workday
iptables -A OUTPUT -d <workday_endpoint> -p tcp --dport 443 -j ACCEPT

# Allow internal network
iptables -A OUTPUT -d 10.0.0.0/8 -j ACCEPT
```

## 3. Claude Code Permissions

In the Claude Code settings, restrict tool access:

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Edit",
      "Write",
      "Bash(python3 *)",
      "Bash(node *)",
      "Bash(git status)",
      "Bash(git diff)",
      "Bash(git log *)"
    ],
    "deny": [
      "WebFetch",
      "Bash(curl *)",
      "Bash(wget *)",
      "Bash(ssh *)",
      "Bash(scp *)",
      "Bash(git push *)",
      "Bash(git remote *)"
    ]
  }
}
```

## 4. Credential Management

- Store API keys as environment variables, not in files
- Use read-only API tokens where possible (e.g., Salesforce read-only profile)
- Rotate credentials on a regular schedule
- Do not place credentials for non-approved services on the VM

## 5. Monitoring

- Log all outbound connection attempts (allowed and blocked)
- Log Claude Code sessions and tool calls (usage tracking)
- Alert on repeated blocked connection attempts (may indicate prompt injection)

## Summary

| Risk                          | Mitigation                              |
|-------------------------------|-----------------------------------------|
| Exfiltration via HTTP         | Network allowlist blocks unapproved sites |
| Prompt injection from web     | WebFetch and curl/wget disabled           |
| Data leakage via clipboard    | Remote access with clipboard disabled     |
| Credential theft              | Scoped, read-only tokens only             |
| Unauthorized API access       | Firewall + credential scoping             |
