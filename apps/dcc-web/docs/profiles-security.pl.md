# Profile, szyfrowane klucze i odzyskiwanie konta

## Kreator profilu

Wybierz Profile → Nowy profil. Kreator prowadzi przez połączenie, uwierzytelnianie, test i uprawnienia. Pokazuje tylko pola właściwe dla wybranego połączenia. Możesz świadomie zapisać profil bez testu. Nowe i importowane profile domyślnie mają wyłącznie odczyt.

Dla SSH/Balena wgraj wybrany klucz oraz zaufany known_hosts. Panel rozpoznaje klucze po zawartości, także bez rozszerzenia, i pomija SSH config oraz inne pliki. Sprawdź nazwy i odciski. Jeśli klucz ma passphrase, wpisz ją ręcznie w profilu.

## Szyfrowanie i usuwanie

Hasła profili, klucze prywatne, sekrety TOTP i SMTP są szyfrowane Fernet. Wgrane klucze prywatne trafiają do zaszyfrowanej bazy, a nie jako jawne pliki do /data/ssh. Klucze publiczne i known_hosts są plikami publicznymi. Migracja sprawdza zaszyfrowaną kopię; katalogi zewnętrzne nie są przenoszone ani kasowane. Odszyfrowanie klucza następuje w pamięci przy połączeniu.

Zaznacz klucze i wybierz Usuń wybrane pliki, sprawdź podgląd profili, a następnie potwierdź. Usuwane są wyłącznie wybrane pliki z magazynu, a terminale zależnych profili są zamykane. Kontenery, wolumeny i pozostałe profile zostają. Operacja nie usuwa klucza z authorized_keys zdalnego hosta.

W Windows klucz główny chroni DPAPI użytkownika usługi; w Linux jest to prywatny plik z prawami 0600. Administrator hosta lub Docker mający klucz główny i bazę może odszyfrować dane. Chroń wolumeny, kopie zapasowe i prawa dostępu. 2FA nie zastępuje ochrony hosta.

## Import i eksport

Import przyjmuje JSON z Desktop lub szyfrowaną kopię Web. Wybierz profile w podglądzie; domyślne dopasowanie nazwy wcześniej wgranego klucza jest opcjonalne. Niedopasowane ścieżki pozostają do ręcznego wyboru, duplikaty są pomijane, istniejące profile nie są nadpisywane. Starszy jawny JSON nie przenosi sekretów.

Eksport wymaga osobnego hasła o długości co najmniej 12 znaków, hasła konta i kodu 2FA, jeśli jest aktywne. Można dołączyć zapisane sekrety i zarządzane klucze. Dowolne pliki hosta ani klucze agenta nie są pobierane. Kopia używa Scrypt i uwierzytelnionego szyfrowania Fernet. Import przywraca prawa tylko do odczytu; odszyfrowanie odbywa się w pamięci.

## SSH Agent i katalog hosta

Agent podpisuje uwierzytelnienie, ale nie umożliwia eksportu klucza ani passphrase. Opcja SSH Agent jest pokazana wyłącznie, gdy agent z kluczami jest osiągalny dla procesu DCC Web. Kontener Linux nie może bezpośrednio użyć potoku Windows OpenSSH; użyj jawnie skonfigurowanego mostu Unix/WSL albo wgraj klucz. Zobacz [instrukcję agenta](configuration.md#ssh-agent).

Dla kontenera ze Sklepu wybierz Podłącz folder hosta. Panel sprawdzi ścieżkę na tym samym hoście Docker i poprosi o potwierdzenie odtworzenia wyłącznie kontenera DCC Web z montowaniem read-only do /mnt/dcc-ssh. Obraz, środowisko, porty i wolumeny są zachowane; terminale rozłączą się na czas operacji. Profile z szyfrowanym magazynem pozostają bez zmian. Katalog zewnętrzny chroni host i passphrase klucza, nie magazyn DCC Web.

Instalacja Compose wymaga samodzielnego dopisania montowania do istniejącego pliku Compose, z zachowaniem ustawień usługi. Przeglądarka nie otwiera folderu serwera w lokalnym Explorerze; przesyłanie plików otwiera lokalny selektor.

## 2FA i odzyskiwanie

W Ustawienia → Administracja i bezpieczeństwo włącz 2FA, wpisz hasło i dodaj sekret do Google Authenticator lub innej aplikacji zgodnej z TOTP/RFC 6238. Potwierdź kodem. Sekret nie jest przekazywany zewnętrznej usłudze QR. Zapisz jednorazowe kody odzyskiwania poza panelem. Włączenie/wyłączenie unieważnia pozostałe sesje.

Wyłączenie wymaga hasła i aktualnego kodu albo kodu odzyskiwania. Odzyskiwanie przez email wymaga wcześniej zweryfikowanego adresu, hasła i skonfigurowanego SMTP z TLS. Panel nie uruchamia SMS ani płatnej wysyłki. Bez emaila użyj kodu odzyskiwania.

## Domeny i publiczne HTTPS

Domenę lokalną dodaj do DNS routera lub hosts; panel nie konfiguruje routera. Opcjonalne rozszerzenie Caddy może pobrać certyfikat HTTPS i utrzymywać go, jeśli posiadasz domenę, DNS wskazuje hosta, a porty 80/443 są osiągalne. W przeciwnym razie, np. za CGNAT, potrzebny jest własny tunel/VPN/reverse proxy. Ustaw mocne hasło i 2FA przed wystawieniem panelu.