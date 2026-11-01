"""Small server-rendered authentication/shell dictionary; operational views use i18n.js."""
EN={
'logowanie':'sign in','Nazwa użytkownika':'Username','Hasło':'Password','Pierwsze uruchomienie':'First launch','Witaj ponownie':'Welcome back',
'Utwórz administratora. Wybierz własne hasło — nie ma hasła domyślnego.':'Create an administrator with your own password. There is no default password.',
'Zaloguj się, aby otworzyć swoje profile Docker.':'Sign in to open your Docker profiles.',
'Utwórz bezpieczną przestrzeń':'Create your secure workspace','Otwórz DCC Web':'Open DCC Web',
'Twoje środowisko.':'Your environment.','W dobrych rękach.':'In good hands.',
'Kontenery, profile i aplikacje w jednym, spokojnym miejscu. Kontrola infrastruktury Docker — po Twojej stronie.':'Containers, profiles and applications in one calm workspace. Docker infrastructure under your control.',
'Lokalny panel administracyjny · bez usług śledzących':'Local administration · no tracking services',
'Dostęp do przestrzeni roboczej':'Workspace access','Sesja chroniona · sekrety profili szyfrowane':'Protected session · encrypted profile secrets',
'O DCC Web i dokumentacja':'About DCC Web and documentation','Nazwa: 3–64 znaki. Hasło: co najmniej 12 znaków.':'Username: 3–64 characters. Password: at least 12 characters.',
'Nieprawidłowa nazwa użytkownika lub hasło.':'Invalid username or password.',
'Aktywny profil':'Active profile','Nawigacja główna':'Main navigation','Dokumentacja':'Documentation','Wyloguj':'Sign out','Otwórz menu':'Open menu',
'Przegląd':'Overview','Gotowy do połączenia':'Ready to connect','Odśwież':'Refresh','Otwieranie przestrzeni roboczej…':'Opening your workspace…','Twoje profile. Twoje dane.':'Your profiles. Your data.','lokalna przestrzeń':'local workspace',
'Asystent AI':'AI assistant','informacje':'about','Docker Control Center,':'Docker Control Center,','w Twojej przeglądarce.':'in your browser.',
'Niezależny moduł projektu DCC. Zarządzaj kontenerami, połączeniami i katalogiem aplikacji z jednego, bezpiecznego miejsca.':'An independent DCC module. Manage containers, connections and application catalogs in one secure workspace.',
'Otwórz przestrzeń roboczą →':'Open workspace →','Dokumentacja lokalna':'Local documentation',
'Instalacja i uruchamianie':'Installation and startup','Profile i konfiguracja':'Profiles and configuration','Bezpieczeństwo':'Security','Sklep i katalogi':'Store and catalogs','Motywy i dźwięki':'Themes and audio','Macierz funkcji desktop / web':'Desktop / Web feature matrix','Testy i ograniczenia':'Tests and limitations',
'DCC Web rozwija się niezależnie od DCC Desktop. Zmiana katalogu lub motywu Web nie wymaga przebudowania desktopu. MCP: stdio tylko do odczytu; Streamable HTTP jest planowany.':'DCC Web evolves independently from Desktop. Catalog and theme changes do not require a Desktop rebuild. MCP supports read-only stdio; Streamable HTTP is planned.'
}

def translate(value,language):
    return EN.get(value,value) if language=='EN' else value
