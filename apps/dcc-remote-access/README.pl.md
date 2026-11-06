# DCC Remote Access 0.1.0

Moduł umożliwia dostęp przez HTTPS do lokalnego DCC Web w przeglądarce. Publiczny adres zapewnia hostowana usługa zrok 2 firmy NetFoundry. Tunel nie wymaga publicznego IP, przekierowania portów, własnej domeny ani klienta VPN i jest domyślnie wyłączony.

## Instalacja i aktywacja

W sklepie DCC Desktop wybierz **DCC Web**. Osobną pozycję **DCC Remote Access** znajdziesz w sklepie przeglądarkowego panelu DCC Web, który zarządza tunelem.

1. Użyj opublikowanego obrazu DCC Web 0.2.6 lub nowszej wersji z Remote Access. Aby zaktualizować panel, wybierz istniejący kontener DCC Web w DCC Container Updater, sprawdź aktualizacje i zastosuj proponowany obraz. Odśwież panel pod dotychczasowym adresem. Przy nowej instalacji skorzystaj z [instrukcji kontenerowej DCC Web](../dcc-web/docs/installation.pl.md).
2. Zaloguj się lokalnie jako administrator. W profilu lokalnego Dockera włącz **Instalowanie aplikacji**. W **Ustawienia → Administracja i bezpieczeństwo → Logowanie i uwierzytelnianie 2FA** skonfiguruj aplikację TOTP i zapisz kody odzyskiwania.
3. Zainstaluj **DCC Remote Access** w kategorii **DCC** w sklepie lub otwórz **Ustawienia → Administracja i bezpieczeństwo → Dostęp do panelu i HTTPS (TLS) → Zdalny dostęp przez Internet**. Obie ścieżki zarządzają tą samą instancją.
4. Utwórz konto w [myzrok.io](https://myzrok.io/) i skopiuj token konta z kreatora konsoli zrok. Otwórz lokalny panel przez zaufane HTTPS. Kliknij **Skonfiguruj**, wklej token i podaj nazwę publiczną lub pozostaw pole puste, aby wygenerować nazwę. Gdy nazwa jest zajęta, wybierz inną.
5. Kliknij **Włącz dostęp**, przeczytaj informację o udostępnieniu panelu i potwierdź aktualnym hasłem oraz nowym kodem TOTP lub kodem odzyskiwania. Poczekaj na stan **Aktywny** i otwórz adres HTTPS. Zrok może pokazać własną stronę pośrednią przy pierwszej wizycie. Następnie zaloguj się na istniejące konto DCC.

Lokalny panel, domeny i HTTPS Caddy działają niezależnie. [Instrukcja uzyskania tokenu zrok](https://netfoundry.io/docs/zrok/get-started/get-token/)

Jeśli konfiguracja została przerwana po rejestracji środowiska, otwórz ponownie **Skonfiguruj** i zatwierdź podpowiedzianą nazwę. DCC użyje zapisanego środowiska i dokończy istniejącą rezerwację w publicznej domenie zrok.

## Wyłączenie, rotacja i aktualizacja

- **Wyłącz dostęp** zamyka wejście do panelu, zatrzymuje tunel i odwołuje automatyczne wznowienie. Rezerwacja pozostaje dostępna. Bez zgody na wznowienie po restarcie DCC Web publiczne wejście wymaga nowej aktywacji z lokalnego panelu.
- Przy włączaniu lub restarcie zaznacz **Wznawiaj tunel po restarcie DCC Web lub komputera**, jeżeli dostęp ma wracać automatycznie. Osobna zgoda **Wznawiaj tunel po aktualizacjach DCC Web przez Updater** obejmuje kontrolowaną podmianę obrazu. Zaznacz obie opcje, aby objąć aktualizacje i restart komputera. Dotychczasowe instalacje nie otrzymują zgody automatycznie.
- Przerwa w Internecie, DNS lub usłudze zrok pozostawia tunel w trybie ponawiania. Publiczny panel jest zamknięty do ponownej weryfikacji HTTPS. Nieoczekiwane zatrzymanie kontenera jest ponawiane w ramach aktywnej zgody; po restarcie panelu wymaga zapisanej zgody na wznowienie. Blokada obrazu lub usunięcie 2FA administratora unieważnia automatyczne wznowienie.
- Awaryjnie użyj **Wyłącz dostęp** w lokalnym panelu, aby również odwołać automatyczne wznowienie. Samo zatrzymanie kontenera przy aktywnej zgodzie może uruchomić odzyskiwanie połączenia. Jeżeli panel jest niedostępny, najpierw zatrzymaj DCC Web, a potem dokładny kontener oznaczony etykietą `io.dcc.remote-access`. Jeżeli po twardej awarii w konsoli zrok pozostała aktywna publikacja, usuń ją lub odwołaj środowisko. Rezerwację możesz zachować.
- Aby zmienić token, wyłącz dostęp, odinstaluj moduł bez zachowania danych i zainstaluj ponownie z nowym tokenem. Jeżeli poprzedni token stracił ważność, najpierw usuń środowisko i zwolnij nazwę w konsoli zrok. Potwierdź to w oknie odinstalowania.
- **Sprawdź aktualizacje** wyświetla najnowszą stabilną wersję zrok 2. Przed przejściem na zweryfikowane wydanie wyłącz tunel i wykonaj kopię wolumenu DCC Web. Odtwórz kontener z przypiętym obrazem nowego modułu i sprawdź publiczne HTTPS po ponownej aktywacji. Wycofanie polega na zatrzymaniu nowego kontenera i powrocie do poprzedniej zweryfikowanej wersji wraz z zaszyfrowaną konfiguracją. Nie wracaj do zablokowanego digestu.

[Model bezpieczeństwa](SECURITY.md) · [English](README.md)
