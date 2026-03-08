#!/usr/bin/env python3
"""
Aggiungi una nuova ricetta a ricette.md e rigenera ricette.html automaticamente.
Uso: python3 aggiungi_ricetta.py
"""

import re
import json
import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MD_FILE  = os.path.join(BASE_DIR, "ricette.md")
HTML_FILE = os.path.join(BASE_DIR, "ricette.html")
PY_SCRIPT = os.path.join(BASE_DIR, "make_html.py")

# ── colori terminale ──────────────────────────────────────────────────────────
G  = "\033[32m"   # verde
B  = "\033[34m"   # blu
Y  = "\033[33m"   # giallo
R  = "\033[31m"   # rosso
W  = "\033[1m"    # grassetto
RST = "\033[0m"   # reset

def pr(msg):  print(msg)
def ok(msg):  print(f"{G}✔ {msg}{RST}")
def warn(msg): print(f"{Y}⚠  {msg}{RST}")
def err(msg): print(f"{R}✖ {msg}{RST}")
def ask(prompt, default=""):
    suf = f" [{default}]" if default else ""
    val = input(f"{B}{prompt}{suf}:{RST} ").strip()
    return val if val else default

def ask_multiline(prompt):
    """Legge più righe fino a riga vuota doppia (invio due volte)."""
    print(f"{B}{prompt}{RST}")
    print(f"{Y}  (scrivi il testo; premi INVIO due volte per finire){RST}")
    lines = []
    empty_count = 0
    while empty_count < 1:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            empty_count += 1
        else:
            empty_count = 0
            lines.append(line)
    return "\n".join(lines).strip()

def ask_list(prompt):
    """Legge una lista di voci (una per riga) fino a riga vuota."""
    print(f"{B}{prompt}{RST}")
    print(f"{Y}  (un ingrediente per riga; riga vuota per finire){RST}")
    items = []
    while True:
        try:
            line = input("  - ").strip()
        except EOFError:
            break
        if not line:
            break
        items.append(line)
    return items

def ask_sources():
    """Chiede le immagini da associare alla ricetta."""
    img_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    all_imgs = sorted(
        [f for f in os.listdir(BASE_DIR)
         if os.path.splitext(f)[1].lower() in img_exts],
        key=lambda f: os.path.getmtime(os.path.join(BASE_DIR, f)),
        reverse=True
    )

    print(f"\n{B}Immagini da associare alla ricetta{RST}")
    print(f"{Y}  (numero dalla lista o nome file, una per riga; riga vuota per finire){RST}")

    if all_imgs:
        n_show = min(15, len(all_imgs))
        print(f"{Y}  Immagini disponibili (più recenti):{RST}")
        for i, img in enumerate(all_imgs[:n_show], 1):
            print(f"    {i:2}. {img}")
        if len(all_imgs) > n_show:
            print(f"       ... e altre {len(all_imgs) - n_show}")
    else:
        print(f"{Y}  Nessuna immagine trovata nella cartella.{RST}")

    sources = []
    while True:
        try:
            line = input("  📷 ").strip()
        except EOFError:
            break
        if not line:
            break
        if line.isdigit():
            idx = int(line) - 1
            if 0 <= idx < len(all_imgs):
                fname = all_imgs[idx]
                if fname not in sources:
                    sources.append(fname)
                    ok(f"Aggiunta: {fname}")
                else:
                    warn(f"Già presente: {fname}")
            else:
                warn(f"Numero non valido (1-{len(all_imgs)}).")
        else:
            if os.path.exists(os.path.join(BASE_DIR, line)):
                if line not in sources:
                    sources.append(line)
                    ok(f"Aggiunta: {line}")
                else:
                    warn(f"Già presente: {line}")
            else:
                warn(f"File non trovato nella cartella: {line}")

    return sources

def categorize(name, ingredients, preparation):
    """Assegna categoria in base a parole chiave."""
    text = (name + " " + " ".join(ingredients) + " " + preparation).lower()
    if any(w in text for w in ["torta","cake","biscotti","ciambella","crostata",
            "banana bread","muffin","brownie","cheesecake","dolce","pancake",
            "crepes","tiramisù","gelato","panna cotta","budino","semifreddo",
            "cinnamon roll","cannolo","mousse","pan di spagna","colomba",
            "pandolce","waffle","marmellata","caramello"]):
        return "Dolci"
    if any(w in text for w in ["pasta","gnocchi","lasagne","risotto","spaghetti",
            "tagliatelle","linguine","penne","rigatoni","fusilli","zuppa",
            "minestra","minestrone","ramen","noodle","ravioli","tortellini",
            "orecchiette","soup","brodo","vellutata"]):
        return "Primi"
    if any(w in text for w in ["pane","pizza","focaccia","piadina","crackers",
            "grissini","flatbread","naan","tigelle","panino","brioche",
            "ciabatta","schiacciata"]):
        return "Pane & Pizza"
    if any(w in text for w in ["pesto","salsa","hummus","condimento","maionese",
            "tzatziki","guacamole","vinaigrette","dressing","burro veg",
            "formaggio veg","ricotta veg","crema spalmabile"]):
        return "Salse & Condimenti"
    if any(w in text for w in ["burger","polpette","polpettone","cotolette","tofu",
            "tempeh","frittata","seitan","terrina","medaglioni","curry",
            "nuggets","arrosto","spezzatino","stufato"]):
        return "Secondi"
    if any(w in text for w in ["porridge","granola","colazione","muesli","overnight"]):
        return "Colazione"
    return "Contorni"

# ── lettura ricette esistenti dall'HTML ───────────────────────────────────────
def load_recipes_from_html():
    if not os.path.exists(HTML_FILE):
        return []
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'/\*RS\*/(.*?)/\*RE\*/', content, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except Exception:
        return []

# ── aggiornamento HTML ─────────────────────────────────────────────────────────
def update_html(recipes):
    if not os.path.exists(HTML_FILE):
        warn("ricette.html non trovato.")
        return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    new_json = json.dumps(recipes, ensure_ascii=False, indent=2)

    # IMPORTANTE: usare lambda per evitare che re.sub interpreti \n nel JSON
    # come newline reali nella stringa di sostituzione
    new_content = re.sub(
        r'/\*RS\*/(.*?)/\*RE\*/',
        lambda m: f'/*RS*/{new_json}/*RE*/',
        content,
        flags=re.DOTALL
    )

    # aggiorna il contatore nell'header
    new_content = re.sub(
        r'(\d+) ricette</span>',
        f'{len(recipes)} ricette</span>',
        new_content
    )

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

# ── aggiunta al file Markdown ──────────────────────────────────────────────────
def append_to_md(recipe):
    sources_yaml = json.dumps(recipe.get("sources", []), ensure_ascii=False)
    block = f"""
---
name: {recipe['name']}
uncertain: false
sources: {sources_yaml}
"""
    if recipe.get("servings"):   block += f"servings: {recipe['servings']}\n"
    if recipe.get("prep_time"):  block += f"prep_time: {recipe['prep_time']}\n"
    if recipe.get("cook_time"):  block += f"cook_time: {recipe['cook_time']}\n"
    if recipe.get("temperature"):block += f"temperature: {recipe['temperature']}\n"
    block += "---\n\n## Ingredienti\n\n"
    for ing in recipe["ingredients"]:
        block += f"- {ing}\n"
    block += f"\n## Preparazione\n\n{recipe['preparation']}\n"
    if recipe.get("notes"):
        block += f"\n## Note\n\n{recipe['notes']}\n"
    block += "\n---\n"

    with open(MD_FILE, "a", encoding="utf-8") as f:
        f.write(block)

# ── UI principale ─────────────────────────────────────────────────────────────
def main():
    os.system("clear" if os.name == "posix" else "cls")
    print(f"\n{W}🌿 Aggiungi una nuova ricetta{RST}\n")

    # ── dati obbligatori ──────────────────────────────────────────────────────
    name = ""
    while not name:
        name = ask("Nome della ricetta")
        if not name:
            warn("Il nome è obbligatorio.")

    ingredients = []
    while not ingredients:
        ingredients = ask_list("Ingredienti")
        if not ingredients:
            warn("Inserisci almeno un ingrediente.")

    preparation = ""
    while not preparation:
        preparation = ask_multiline("Preparazione")
        if not preparation:
            warn("La preparazione è obbligatoria.")

    # ── dati opzionali ────────────────────────────────────────────────────────
    pr(f"\n{Y}Dati opzionali (premi INVIO per saltare){RST}")
    servings    = ask("Porzioni (es. 4 persone)")
    prep_time   = ask("Tempo preparazione (es. 20 minuti)")
    cook_time   = ask("Tempo cottura (es. 30 minuti)")
    temperature = ask("Temperatura forno (es. 180°C)")
    notes       = ask("Note aggiuntive")
    sources     = ask_sources()

    # ── costruzione oggetto ───────────────────────────────────────────────────
    category = categorize(name, ingredients, preparation)

    recipe = {
        "name":        name,
        "category":    category,
        "uncertain":   False,
        "uncertainty_reason": "",
        "sources":     sources,
        "servings":    servings,
        "prep_time":   prep_time,
        "cook_time":   cook_time,
        "temperature": temperature,
        "ingredients": ingredients,
        "preparation": preparation,
        "notes":       notes,
    }

    # ── riepilogo ─────────────────────────────────────────────────────────────
    print(f"\n{W}── Riepilogo ──────────────────────────────{RST}")
    print(f"  Nome:       {name}")
    print(f"  Categoria:  {category}")
    print(f"  Ingredienti:{len(ingredients)}")
    if servings:    print(f"  Porzioni:   {servings}")
    if prep_time:   print(f"  Prep:       {prep_time}")
    if cook_time:   print(f"  Cottura:    {cook_time}")
    if temperature: print(f"  Temp:       {temperature}")
    if sources:     print(f"  Immagini:   {len(sources)} ({', '.join(sources)})")
    else:           print(f"  Immagini:   nessuna")
    print()

    confirm = ask("Salvare la ricetta? (s/n)", default="s").lower()
    if confirm not in ("s", "si", "sì", "y", "yes"):
        warn("Operazione annullata.")
        sys.exit(0)

    # ── salvataggio ───────────────────────────────────────────────────────────
    pr(f"\n{W}Salvataggio...{RST}")

    # 1. Aggiunge al markdown
    append_to_md(recipe)
    ok(f"Ricetta aggiunta a ricette.md")

    # 2. Aggiunge all'HTML
    recipes = load_recipes_from_html()
    next_id = max((r.get("id", 0) for r in recipes), default=-1) + 1
    recipe["id"] = next_id
    recipes.append(recipe)
    update_html(recipes)
    ok(f"ricette.html aggiornato ({len(recipes)} ricette totali)")

    print(f"\n{W}✅ Fatto! Ricorda di sostituire ricette.html su Google Drive.{RST}\n")

if __name__ == "__main__":
    main()
