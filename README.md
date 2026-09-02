# Console de l'orgue relevé

Extraction des **notes** et des **timbres** d'un enregistrement d'orgue, et
application web qui rejoue l'instrument à partir de ce relevé.

Tout ce que joue l'application — hauteurs, durées, équilibre sonore, couleur de
chaque registration, diapason, acoustique du lieu — a été mesuré sur
l'enregistrement. Rien n'est un réglage d'usine.

```
analysis/   chaîne d'analyse (Python)          app/    application web
tools/      assemblage en fichier unique       docs/   extraits sonores
```

## Ce que l'enregistrement contenait

L'enregistrement fourni dure **14 min 44 s**. L'analyse y a trouvé :

| | |
|---|---|
| Musique jouée | **501 s** répartis en 15 extraits |
| Commentaire parlé | **383 s**, écartés automatiquement |
| Diapason | **La₄ = 445,1 Hz** (+19,8 cents), tempérament proche de l'égal |
| Réverbération | **RT60 ≈ 4,5 s** — un grand vaisseau de pierre |
| Notes transcrites | **2 928** |
| Registrations distinctes | **7** |

C'est une démonstration commentée : l'organiste joue, puis parle. Le premier
travail de la chaîne est donc de **séparer la parole de la musique** — sans
quoi chaque phonème devient une gerbe de fausses notes (le premier passage
produisait 21 notes par seconde sur les passages parlés).

### Les registrations retrouvées

| # | Nom déduit | Rangs qui sonnent | Présence | Attaque |
|---|---|---|---|---|
| 1 | Nazard / Grand jeu | 8′ 4′ 2⅔′ 2′ 1⅗′ 1⅓′ 1′ | 159 s | 160 ms |
| 2 | Flûte / Fonds doux | 8′ | 37 s | 160 ms |
| 3 | Principal / Montre | 8′ 4′ | 40 s | 123 ms |
| 4 | Flûte / Fonds doux | 8′ 4′ | 98 s | 32 ms |
| 5 | Principal / Montre | 8′ 4′ | 10 s | 40 ms |
| 6 | Principal / Montre | 8′ 4′ | 112 s | 121 ms |
| 7 | Principal / Montre | 16′ 8′ 4′ 2⅔′ 2′ 1′ | 55 s | 43 ms |

Les noms sont une **interprétation** de la forme du spectre, pas une lecture de
la console : un rang de 4′ tiré et la deuxième harmonique d'un 8′ produisent
exactement le même partiel. Ce qui est mesuré, et donc fiable, c'est
l'amplitude de chacun des 32 partiels — c'est elle que rejoue l'application.

## L'application

```bash
cd app && python3 -m http.server 8000     # puis http://localhost:8000
```

ou, en un seul fichier à ouvrir par double-clic :

```bash
python3 tools/build_standalone.py         # écrit dist/orgue.html
```

- **Écouter** la transcription : rouleau défilant, registration courante affichée,
  bandeau de navigation montrant toute la séance (extraits joués en couleur,
  densité de notes en dessous).
- **Jouer** l'orgue : souris ou doigt sur les touches, rangées `QSDFGHJKLM` et
  `ZERTYUOP` du clavier d'ordinateur, `←`/`→` pour l'octave, ou un vrai clavier
  MIDI via le bouton *Clavier MIDI*.
- **Tirer un jeu** : chaque bouton de registre sélectionne un des timbres relevés.
- **Modifier le timbre** : les 32 barres de la composition harmonique se
  déplacent à la souris, le son change immédiatement.
- **Exporter** le MIDI depuis la page, ou prendre `app/data/orgue.mid`
  (une piste par registration).

La synthèse est **additive** : un oscillateur par note, dont l'onde périodique
porte les 32 partiels mesurés. L'onde est construite sur f₀/2, ce qui rend
exacts les rapports demi-entiers du relevé — dont le 16′ et ses harmoniques.
S'y ajoutent l'attaque et la relâche mesurées, un léger désaccord par tuyau, le
souffle d'attaque, et une réverbération à convolution réglée sur le RT60 relevé.

## Refaire l'analyse

```bash
pip install -r analysis/requirements.txt
python3 analysis/transcribe.py enregistrement.m4a -o app/data
python3 analysis/render.py app/data/orgue.json -o rendu.wav   # pour écouter
```

Options utiles : `-r` nombre de registrations à distinguer, `-s` sensibilité de
détection (`>1` retient plus de notes), `-c` élagage des notes peu explicatives,
`--start/--end` pour ne traiter qu'un extrait.

## Comment ça marche

1. **Parole / musique** (`content.py`) — trois traits par demi-seconde : niveau,
   tenue du spectre à 0,12 s d'intervalle, contraste pic/vallée. Sur cet
   enregistrement le niveau sépare parfaitement les deux (orgue ≥ 0,16 du niveau
   global, parole ≤ 0,065) ; les deux autres rattrapent les jeux doux.
2. **Diapason** (`audio.py`) — moyenne circulaire pondérée de l'écart au demi-ton
   sur tous les pics spectraux saillants, mesurée sur la musique seule.
3. **Timbre et notes conjointement** (`nmf.py`) — le spectrogramme est factorisé
   en `V ≈ W(g)·A + Wn·An`, où le dictionnaire `W(g) = Σ gₖ·Bₖ` est entièrement
   déterminé par le profil harmonique `g`. `g` et les activations `A` sont
   estimés en alternance par mises à jour multiplicatives (divergence de
   Kullback-Leibler). Quelques bases larges `Wn` absorbent le souffle et la
   réverbération pour qu'ils ne deviennent pas des notes.
   Un a priori de Dirichlet sur `g` tranche l'ambiguïté d'octave : « un son riche
   à f » et « des sons purs à f, 2f, 4f » expliquent le même spectre, et sans lui
   le timbre estimé dégénère en sinusoïde.
4. **Registrations** (`timbre.py`) — un profil est estimé par bloc de 8 s, les
   blocs sont regroupés par k-moyennes sur les profils en dB, puis chaque
   registration est nommée d'après la pente de décroissance des harmoniques,
   le poids des partiels 5-7-9-11 (« anchité ») et les rangs qui sonnent.
5. **Événements** (`notes.py`) — suivi par hystérésis sur l'énergie par hauteur,
   avec un seuil qui suit la sonorité locale et un plancher rapporté à tout
   l'enregistrement, une exigence de saillance face aux demi-tons voisins, puis
   un élagage des notes dont le retrait ne dégrade pas la reconstruction.

## Ce que vaut le relevé

Comparaison entre l'enregistrement et sa resynthèse, extrait par extrait :

| | médiane |
|---|---|
| Similarité de chroma (classes de hauteur) | **0,91** |
| Similarité de CQT (hauteur **et** octave) | **0,80** |
| Témoin — deux passages sans rapport | 0,33 |

`docs/comparaison-original-vs-releve.mp3` fait entendre trois extraits, chacun
d'abord dans l'enregistrement puis dans sa resynthèse.

### Limites

- Les noms de jeux sont déduits du spectre, pas lus sur la console.
- Les octaves graves restent le point faible de toute transcription
  polyphonique : un 16′ au fondamental faible peut se lire une octave trop bas.
- La transcription ne distingue pas les claviers ; la séparation
  manuel / pédale exportée dans le JSON est une heuristique de registre.
- Les passages les plus fournis restent sur-détectés : là où huit rangs sonnent
  ensemble, une note tenue et ses harmoniques ne sont pas toujours séparables.
