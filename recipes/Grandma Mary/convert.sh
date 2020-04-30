#!/bin/bash

header='
<head>
<style>
@media print {
  @page {
    size: 8in 6in;
    margin: 0in;
    padding: 0in;
  } 
  body {
    padding: 0in;
    margin: 0in;
  }
  article {
    width: 6.5in;
    height: 4.5in;
    margin: 0.5in;
    padding: .25in;
  }
}
@media screen {
  article {
    margin-top: 1em;
    padding: 1em;
  }
  body {
    max-width: 8in;
    margin: auto;
  }
}
article {
  max-width: 7in;
  border-style: solid;
}
main {
  display: grid;
  grid-template-columns: auto auto;
  justify-content: space-around;
  grid-column-gap: 2em;
}
dt::after {
  content: ": ";
}
dl {
  margin-left: 1em;
  margin-right: 1em;
  display: grid;
  grid-template-columns: auto auto auto;
  justify-content: space-between;
}
dt {
  display: inline;
}
dd {
  display: inline;
  margin-inline-start: 0px;
}
h1 {
  page-break-before: always;
  margin-block-start: 0.0em;
  margin-block-end: 0.5em;
}
h2 {
  margin-block-start: 0.0em;
  margin-block-end: 0.5em;
}
h3 {
  margin-block-start: 0.5em;
  margin-block-end: 0.5em;
}
h4 {
  margin-block-start: 0.5em;
  margin-block-end: 0.5em;
}
#subtitle {
  margin-left: 1em;
}
</style>
</head>
'

entries=''
body=''
while read line; do
  recipe="$(./convert_one.sh "${line}")"
  entries="${entries}$(echo; echo "${recipe}" | head -1)"
  recipe_body="$(echo "${recipe}" | tail -n +2)"
  echo "${header}${recipe_body}" > "${line%.wdb}.html"
  body="${body}${recipe_body}"
done < <(find . -name "*.wdb" | sort | tail -5)

_last_category=''
toc=$(echo "${entries}" |
  sort -k 1,2 -t $'\t' |
  while IFS=$'\t' read category recipe_name; do
    if [[ "${category}" != "${_last_category}" && ! -z "${_last_category}" ]]; then
      echo '<ol>'
    fi
  done)

echo "${header}${body}" > recipes.html

echo "${entries}"

echo "${toc}"
