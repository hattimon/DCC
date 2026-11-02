# Wspólny Sklep i katalog aplikacji

Główny dcc-catalog.json zawiera pojedyncze definicje aplikacji, w tym DCC Web. Dodatkowe repozytoria GitHub, adresy HTTPS JSON i wgrane pliki używają formatu Desktop. Obsługiwane są nazwy dcc-catalog.json i catalog.json. Plik wgrywa się przez panel; nie otwiera się dowolnej ścieżki serwera.

category/category_en to starsze pola głównej kategorii. Opcjonalne categories/categories_en dodają kolejne kategorie bez kopiowania wpisu aplikacji. Desktop i Web korzystają ze wspólnych helperów dcc_catalog.py. Kolejność kategorii to Wszystkie → Zainstalowane → DCC → AI; DCC jest pogrubione. DCC Container Updater zachowuje Aktualizacje/Updates i dodatkowo należy do DCC. Identyfikatory i konfiguracja instalacji pozostają takie same.

    {"apps":[{"name":"Przykładowe rozszerzenie","image":"example/extension:1","category":"Narzędzia","categories":["DCC"]}]}

To przykład dokumentacyjny, nie fikcyjna aplikacja w katalogu. Oficjalne rozszerzenia powinny mieć DCC i pasujące kategorie funkcjonalne. Źródła można sprawdzać, odświeżać, włączać, wyłączać i usuwać; oficjalnego katalogu nie da się wyłączyć. Przy błędzie sieci pozostaje cache. Serwery CLI odświeżają co godzinę i ręcznie; wgrany plik zastępuje się ponownym wgraniem.

## Jedna aplikacja i najnowszy wpis

DCC Web 0.1.4 scala wersje po nazwie, repozytorium obrazu bez tagu/digestu i domyślnej nazwie kontenera. Kategorie nie tworzą oddzielnych wpisów. Wersje z liczbowymi tagami są porównywane numerycznie, więc starszy cache nie obniży nowszej wersji w tym samym źródle. Dla tagów ruchomych, takich jak latest, i digestów obowiązuje kolejność źródeł. Warianty z różnymi nazwami kontenerów lub repozytoriami pozostają odrębne.

Każda aplikacja/wariant powinna występować raz. CI odrzuca duplikaty. Przy nowym wydaniu aktualizuj istniejący wpis. DCC Web wskazuje tagi dcc-web-vX.Y.Z; przed zmianą sprawdza się obrazy amd64 i arm64.

## Wsteczna zgodność

Schema katalogu pozostaje wersją 1. DCC Web ma główną kategorię Administracja oraz dodatkowe DCC i WWW. Updater zachowuje główną kategorię Aktualizacje. Starszy klient czytający wyłącznie główną kategorię nadal może znaleźć aplikację funkcjonalnie.

Starsze pliki Desktop identyfikowały wpis po nazwie i pełnym tagu obrazu, więc wbudowany DCC Web 0.1.0 może występować obok nowszego wpisu sieciowego. Odświeżenie katalogu nie może zmienić tego zachowania — wymaga to aktualizacji klienta. Niezależny Sklep w kontenerowym DCC Web może zaktualizować swój katalog bez publikacji EXE/DEB. Nie nadpisuje się istniejących tagów wydań.

Przed instalacją panel sprawdza architekturę, RAM, porty, konflikt nazw i dozwolone opcje. Podgląd pokazuje polecenie Docker i ostrzeżenia o socketach/uprawnieniach/trwałości. Skryptów z metadanych katalogu nie uruchamia automatycznie. Budowanie ze źródeł wymaga osobnej weryfikacji repozytorium i Dockerfile.

Kontrola portów sprawdza mapowania Docker i proponuje alternatywy. Automatyczny wybór jest potwierdzany w podglądzie; Docker wykonuje ostateczne sprawdzenie. Odinstalowanie usuwa kontenery bez -v. Dane w warstwie zapisywalnej kontenera nie są trwałe. Brak uprawnienia install jest wyjaśniany administratorowi.