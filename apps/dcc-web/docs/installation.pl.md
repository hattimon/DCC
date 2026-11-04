# Instalacja DCC Web 0.2.0

DCC Web działa w Windows, macOS i Linux z rodziny Debian. Wymaga Docker Engine/Docker Desktop z Compose v2 albo Python 3.12 w instalacji natywnej.

## Instalator Docker Compose

Pobierz i rozpakuj [archiwum źródłowe DCC Web](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.2.0/DCC-Web-0.2.0-source.zip), otwórz terminal w katalogu DCC-Web-0.2.0 i uruchom:

```
py -3.12 apps/dcc-web/install.py
```

W macOS/Linux użyj: python3 apps/dcc-web/install.py.

Używany jest lokalny kontekst Docker. Instalator sprawdza porty Dockera i dostępność lokalnego nasłuchu; preferuje 8789, a gdy port jest zajęty skanuje 8790–8888. Wybrany port zapisuje dla bieżącego użytkownika. W razie wyścigu o port ponawia próbę. Pobiera obraz wieloarchitekturowy, tworzy konto administratora, uruchamia usługę i wyświetla adres panelu.

Panel jest domyślnie dostępny tylko lokalnie, a dane przechowuje w wolumenie dcc_web_data. Istniejący kontener dcc-web-standalone pozostaje bez zmian. Dostęp do socketu Docker pozwala panelowi zarządzać hostem, więc należy go udostępniać tylko zaufanym administratorom.

## Instalacja ze Sklepu DCC

W DCC Desktop 1.3.11 lub nowszym przejdź do Sklep aplikacji → DCC, wybierz DCC Web i kliknij Zainstaluj. DCC wybiera wolny port i wyświetla adres. Instalacja działa na wybranym profilu Docker. Pierwsze uruchomienie tworzy konto admin z losowym hasłem; wynik instalacji pokazuje je, a logi kontenera zachowują kopię. Zmień hasło po zalogowaniu.

## Uruchomienie natywne przez Python

Wymaga Python 3.12 i Docker CLI. Z katalogu projektu uruchom:

```
py -3.12 -m venv .venv-dcc-web
.venv-dcc-web\Scripts\python.exe -m pip install -r apps/dcc-web/requirements.txt
.venv-dcc-web\Scripts\python.exe apps/dcc-web/web.py --host 127.0.0.1 --port 8789
```

Na macOS/Linux ścieżka interpretera to .venv-dcc-web/bin/python. Domyślne dane są w ~/.dcc-web; opcja --data PATH wybiera inny katalog. Jeśli 8789 jest zajęty, wybierz inny port.

## Dostęp zdalny

Nie wystawiaj panelu Docker bezpośrednio do Internetu. Użyj zaufanego reverse proxy HTTPS lub VPN oraz silnego hasła. Profil sklepu musi mieć uprawnienie Instalowanie aplikacji.

Lokalne HTTPS włączysz w **Ustawienia → Administracja i bezpieczeństwo → Domena lokalna i publiczna**. Podaj prywatny adres IP hosta (zalecane) albo nazwę z lokalnego DNS, zapisz ustawienia i wybierz **Dostęp HTTPS → Włącz lokalne HTTPS**. Zarządzane rozszerzenie Caddy zachowuje obecny adres HTTP i wolumen danych, wiąże port tylko z tym prywatnym/loopback adresem oraz wybiera wolny port z zakresu 9443–9499. Otwórz wyświetlony adres HTTPS, pobierz lokalny certyfikat CA i zainstaluj/zaufaj mu na urządzeniu klienckim. Publiczne HTTPS jest osobną opcją wymagającą domeny oraz osiągalnych portów 80/443.
