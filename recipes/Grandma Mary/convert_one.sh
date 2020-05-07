#!/bin/bash
recipe="$1"

csv=$(unoconv -f csv --stdout "${recipe}")

# Recipe Name,Category,Ingredient 1,...Ingredient 12,Instructions,Prep time,Servings,Author
function extract() {
  echo "${csv}" | csvtool col "$1" -
}

function escape() {
  sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&#39;/g'
}

function rawcell() {
  extract "$1" | csvtool format '%1' -
}

function cell() {
  rawcell "$1" | escape
}

recipe_name=$(cell '1')
category=$(cell '2')
instructions=$(cell '15')
prep_time=$(cell '16')
servings=$(cell '17')
author=$(cell '18')

num_ingredients=$(extract '3-14' | csvtool trim r - | csvtool width -)

last_ingredient="$(rawcell $(( 3 + ${num_ingredients} - 1 )) )"
instructions="$(strings "${recipe}" | sed -n -e "/^ *${last_ingredient//\//\\\/} *\$/,/^ *${prep_time//\//\\\/} *\$/p" | tail -n +2 | head -n -1)"

echo -e "${category}\t${recipe_name}"
cat <<EOF
<article>
  <header>
    <h1>${recipe_name}</h1>
    <h4 id="subtitle">From the kitchen of ${author}</h4>
    <dl id="metadata">
      <div><dt>Category</dt><dd>${category}</dd></div>
      <div><dt>Preparation time</dt><dd>${prep_time}</dd></div>
      <div><dt>Servings</dt><dd>${servings}</dd></div>
    </dl>
  </header>
  <hr/>
  <main>
  <section>
    <h2>Ingredients</h2>
    <ul>
EOF

for i in $(seq 3 1 $(( 2 + ${num_ingredients} )) ); do
  echo "      <li>$(cell "$i")</li>"
done

cat <<EOF
    </ul>
  </section>
  <section>
    <h2>Instructions</h2>
    <p>${instructions}</p>
  </section>
  </main>
</article>
EOF
