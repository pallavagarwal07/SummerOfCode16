qgrep -Hx 'KEYWORDS="[^"]*~amd64[ "]' > packages
tmp="$(cat packages | sed -r 's/^(.*?):.*/\1/g')"
echo "$tmp" > packages
sed -ri 's/\/.*\//\//g' packages
sed -ri 's/\.ebuild//g' packages
for i in `cat packages | sort -R`; do
    echo "$i"
    curl -G 'http://162.246.156.59:32000/add-package' -d 'package'="$i"
done
