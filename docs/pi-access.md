# Connecting to the dev Raspberry Pi

How a new session (human or agent) reaches the GhostHand development Pi.

## The Pi

| | |
|---|---|
| Host | `ghosthand.local` (mDNS). Last seen at `192.168.1.125` on Wi-Fi |
| User | `nerginer` |
| SSH key | `~/.ssh/id_rsa` on the Mac (key auth only) |
| Host key | ED25519 `SHA256:doKv8cD5A/WuOUwICRSvfgQ4mMjqgYzw+THoVwslep4` |
| Board | Raspberry Pi 4 Model B Rev 1.5, 8 GB RAM, 16 GB microSD |
| OS | Raspberry Pi OS (Debian 13 "trixie"), aarch64, Python 3.13 |
| sudo | Passwordless |

## Connect

```sh
ssh -i ~/.ssh/id_rsa nerginer@ghosthand.local
```

Run a single command:

```sh
ssh -i ~/.ssh/id_rsa nerginer@ghosthand.local 'uname -a'
```

Copy files:

```sh
scp -i ~/.ssh/id_rsa ./file nerginer@ghosthand.local:~/
rsync -av -e "ssh -i ~/.ssh/id_rsa" ./server/ nerginer@ghosthand.local:~/ghosthand/server/
```

Never put the account password in commands, scripts or docs. Use the key.

## Claude Code permissions

- `.claude/settings.local.json` allows `ssh -i ~/.ssh/id_rsa nerginer@ghosthand.local …`, `scp -i ~/.ssh/id_rsa …` and
  `rsync … ghosthand.local …`. Keep commands in that exact form (`-i ~/.ssh/id_rsa` first, then the host) or they
  won't match the rule.
- A global `deny` rule for `Bash(ssh:*)` in `~/.claude/settings.json` overrides any allow. It was removed to make this
  work; if it comes back, SSH is silently denied with no prompt.
- The user's global rule still applies to every **other** remote host: ask before connecting.

## Troubleshooting

- **`Host key verification failed`:** the host key is missing or changed (e.g. the card was re-flashed). Check with
  `ssh-keygen -F ghosthand.local`. If the Pi was re-flashed, remove the old entry with
  `ssh-keygen -R ghosthand.local`, then add the new one with `ssh-keyscan -t ed25519 ghosthand.local >> ~/.ssh/known_hosts`
  and compare the fingerprint with `ssh-keygen -lf`.
- **`ghosthand.local` doesn't resolve:** check `dscacheutil -q host -a name ghosthand.local`, or find the IP on the
  router. The Pi joins the same Wi-Fi as the Mac and iPhone.
- **Ethernet:** a cable connects the Mac and the Pi directly, but `eth0` has no IP yet (no DHCP on that link). Use Wi-Fi.
