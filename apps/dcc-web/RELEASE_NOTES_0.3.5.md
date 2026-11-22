# DCC Web 0.3.5

## Polski

- MCP podaje powód odmowy dostępu do hosta i wskazuje profile uprawnione do `host_exec`. Kreator profilu pozwala sprawdzić SSH do Windows niezależnie od Dockera.
- Operacje Docker w panelu i MCP współdzielą blokadę aktualizacji dla tego samego profilu. Edycja grantu wykrywa, że inny administrator zapisał zmianę po otwarciu formularza.

## English

- MCP explains host access denials and lists the profiles eligible for `host_exec`. The profile wizard can verify SSH to Windows separately from Docker.
- Docker mutations in the panel and MCP share a lock for each profile. Grant edits detect changes saved after the form was opened.

[DCC-Web-0.3.5-source.zip](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.5/DCC-Web-0.3.5-source.zip)
