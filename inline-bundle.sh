#!/bin/bash
CSS=$(cat dist/assets/index-BcYVLrxo.css)
JS=$(cat dist/assets/index-DFt0kg2p.js)
cat > /sessions/youthful-dazzling-ride/mnt/outputs/tedi-dashboard-v9.html << HTMLEOF
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>TEDi Team Dashboard</title>
<style>${CSS}</style>
</head>
<body>
<div id="root"></div>
<script type="module">${JS}</script>
</body>
</html>
HTMLEOF
echo "Done: tedi-dashboard-v9.html"
