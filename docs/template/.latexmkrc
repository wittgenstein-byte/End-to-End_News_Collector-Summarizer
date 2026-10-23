# XeLaTeX + biber (Overleaf: Menu > Settings > Compiler = XeLaTeX)
$pdf_mode = 5;
$xelatex  = 'xelatex -synctex=1 -interaction=nonstopmode -file-line-error %O %S';
$biber    = 'biber %O %S';
