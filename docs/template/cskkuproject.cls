% =====================================================================
%  cskkuproject.cls  v2 — เล่มรายงานโครงงานคอมพิวเตอร์
%  สาขาวิชาวิทยาการคอมพิวเตอร์ วิทยาลัยการคอมพิวเตอร์ มหาวิทยาลัยขอนแก่น
%
%  รูปแบบทั้งหมดมาจาก cskkucore.sty (ใช้ร่วมกับ cskkumanual.cls)
%  Compile ด้วย XeLaTeX + biber (Overleaf: Compiler = XeLaTeX)
%
%  ตัวเลือก (\documentclass[...]{cskkuproject})
%    progress1 / progress2 / final   ชนิดเล่ม (ค่าเริ่มต้น final)
%    plainnumbering      เลขหัวข้อแบบ 1. / 1.1 / 1.1.1 / (1) (ตัวอย่างหน้า 24 ของคู่มือ)
%    boldheadings        หัวข้อย่อยระดับ 1–3 ตัวหนา (คู่มือกำหนดตัวปกติ)
%    chapterfloats       เลขภาพ/ตารางแยกตามบท (2.1, 2.2) แทนเลขต่อเนื่อง
%    chapterpagenumber   แสดงเลขหน้าในหน้าแรกของบท
%    englishbook         เล่มภาษาอังกฤษทั้งเล่ม (Times)
%    titleasis           ไม่แปลงชื่อเรื่องภาษาอังกฤษบนปกเป็นตัวพิมพ์ใหญ่
%    mermaid             เปิดใช้ mermaid.sty (ต้องใช้ -shell-escape + mmdc)
% =====================================================================
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{cskkuproject}[2026/10/15 v2.0.0 CS KKU Computer Project Report]

\newif\ifcskku@titleasis \cskku@titleasisfalse
\def\cskku@doctypeopt{final}
\DeclareOption{progress1}{\def\cskku@doctypeopt{progress1}}
\DeclareOption{progress2}{\def\cskku@doctypeopt{progress2}}
\DeclareOption{final}{\def\cskku@doctypeopt{final}}
\DeclareOption{titleasis}{\cskku@titleasistrue}
\DeclareOption*{\PassOptionsToPackage{\CurrentOption}{cskkucore}}
\ProcessOptions\relax

% fix-cm: ฟอนต์คณิตศาสตร์ (Computer Modern) ปรับได้ทุกขนาด เช่น 13 bp / 16 bp
\RequirePackage{fix-cm}
\LoadClass[a4paper,oneside,12pt]{report}
\RequirePackage{cskkucore}
\RequirePackage{cskkufront}
% แผนภาพ (TikZ) และสีในเซลล์ตาราง (\cellcolor) สำหรับตัวอย่างในบทที่ 3–4
\RequirePackage{tikz}
\usetikzlibrary{arrows.meta,positioning,calc,shapes.geometric,fit}
\RequirePackage{colortbl}
\definecolor{ganttbar}{gray}{0.62}   % แถบในตารางแผนการดำเนินงาน

% ---------------------------------------------------------------------
% ชนิดเล่ม (บรรทัดที่ 2 บนปก 20 หนา)
% ---------------------------------------------------------------------
\ifdefstring{\cskku@doctypeopt}{progress1}
  {\doctype{รายงานความก้าวหน้าโครงงาน ครั้งที่ 1}}{}
\ifdefstring{\cskku@doctypeopt}{progress2}
  {\doctype{รายงานความก้าวหน้าโครงงาน ครั้งที่ 2}}{}
\ifdefstring{\cskku@doctypeopt}{final}
  {\doctype{เอกสารโครงงานฉบับสมบูรณ์}}{}
\coverstatement{รายงานนี้เป็นส่วนหนึ่งของการศึกษาวิชา}

% ---------------------------------------------------------------------
% บทคัดย่อ (คู่มือข้อ 11, หน้า 14–15)
%   ส่วนหัว: ชื่อผู้เขียน. ปี. ชื่อเรื่อง. โครงงานคอมพิวเตอร์ ปริญญา... สาขาวิชา...
%            อาจารย์ที่ปรึกษา: ...
%   ตามด้วย "บทคัดย่อ" กลางหน้า เนื้อหา และคำสำคัญ
% ---------------------------------------------------------------------
\newcommand\cskku@abstracthead[2]{% #1 = ส่วนหัว, #2 = อาจารย์ที่ปรึกษา
  {\setlength\parindent{0pt}%
   \hangindent=\cskkuIndentA \hangafter=1
   #1\par
   \hangindent=\cskkuIndentA \hangafter=1
   #2\par}}

\newenvironment{abstractTH}{%
  \clearpage
  \phantomsection
  \addcontentsline{toc}{chapter}{บทคัดย่อภาษาไทย}%
  \cskku@abstracthead
    {\cskku@studentlistTH.\ \@submitYearTH.\
     \textbf{\@titleTH.}\ โครงงานคอมพิวเตอร์ ปริญญา\@degreeTH\
     สาขาวิชา\@majorTH\ \@collegeTH\ \@universityTH.}
    {\textbf{อาจารย์ที่ปรึกษา:}\ \@advisorTH
     \ifx\@coadvisorTH\@empty\else\ และ \@coadvisorTH\fi}%
  \vspace{\baselineskip}%
  {\centering\cskkuChapterFont บทคัดย่อ\par}%
  \vspace{\baselineskip}%
  \cskkuSetIndent{\cskkuIndentA}%
  \@afterindenttrue}
 {\par\vspace{\baselineskip}%
  \noindent\textbf{คำสำคัญ:}\ \@keywordsTH\par
  \clearpage}

\newenvironment{abstractEN}{%
  \clearpage
  \phantomsection
  \addcontentsline{toc}{chapter}{บทคัดย่อภาษาอังกฤษ}%
  \cskku@abstracthead
    {\cskku@studentlistEN.\ \the\numexpr\@submitYearTH-543\relax.\
     \textbf{\@titleEN.}\ \@degreeEN\ Project in \@majorEN,
     \@collegeEN, \@universityEN.}
    {\textbf{Project Advisor:}\ \@advisorEN
     \ifx\@coadvisorEN\@empty\else\ and \@coadvisorEN\fi}%
  \vspace{\baselineskip}%
  {\centering\cskkuChapterFont ABSTRACT\par}%
  \vspace{\baselineskip}%
  \cskkuSetIndent{\cskkuIndentA}%
  \@afterindenttrue}
 {\par\vspace{\baselineskip}%
  \noindent\textbf{Keywords:}\ \@keywordsEN\par
  \clearpage}

% ---------------------------------------------------------------------
% กิตติกรรมประกาศ (ข้อ 12) — ลงชื่อผู้จัดทำท้ายหน้าอัตโนมัติ
% ---------------------------------------------------------------------
\newenvironment{acknowledgement}{%
  \clearpage
  \cskkuUnnumberedChapter{กิตติกรรมประกาศ}}
 {\par\vspace{\baselineskip}%
  \begin{flushright}
    \begin{tabular}{@{}c@{}}
      ผู้จัดทำ\\
      \cskku@studentnamesTH
    \end{tabular}
  \end{flushright}%
  \clearpage}

% ---------------------------------------------------------------------
% รายการสัญลักษณ์และคำย่อ (ข้อ 16)
%   \begin{symbols} \symbolitem{API}{Application Programming Interface} \end{symbols}
% ---------------------------------------------------------------------
\newcommand\symbolitem[2]{#1 & คือ & #2\\}
\newenvironment{symbols}{%
  \clearpage
  \cskkuUnnumberedChapter{รายการสัญลักษณ์และคำย่อ}%
  \addtocounter{table}{-1}%
  \setlength\LTleft{0pt}\setlength\LTright{0pt plus 1fill}%
  \renewcommand\arraystretch{1.1}%
  \begin{longtable}{@{}l@{\hspace{1.2em}}c@{\hspace{1.2em}}p{0.7\linewidth}@{}}}
 {\end{longtable}\clearpage}
\let\symbolpage\symbols
\let\endsymbolpage\endsymbols

% ---------------------------------------------------------------------
% ประวัติผู้เขียน (ข้อ 20) — ไม่เกิน 1 หน้า เป็นหน้าสุดท้ายของเล่ม
% ---------------------------------------------------------------------
\newenvironment{biography}{%
  \clearpage
  \cskkuUnnumberedChapter{ประวัติผู้เขียน}}
 {\par\clearpage}

% ---------------------------------------------------------------------
% โครงสร้าง 5 บท (ข้อ 17) — ชื่อบทกำหนดไว้ที่นี่ที่เดียว
% ---------------------------------------------------------------------
\newcommand*\chapteronetitle{บทนำ}
\newcommand*\chaptertwotitle{งานวิจัยและทฤษฎีที่เกี่ยวข้อง}
\newcommand*\chapterthreetitle{วิธีการดำเนินงาน}
\newcommand*\chapterfourtitle{การวิเคราะห์ระบบ และพัฒนาโปรแกรม}
\newcommand*\chapterfivetitle{บทสรุป}
% ทางลัดที่ template เดิมใช้: \chapterone = \chapter{บทนำ} + ไฟล์ chapters/chapter1.tex
% (ถ้าไม่มีโฟลเดอร์ chapters/ จะใช้ chapter1.tex ที่อยู่ข้าง main.tex แบบ template เดิม)
\newcommand\cskku@chapterfile[1]{%
  \IfFileExists{chapters/#1.tex}{\input{chapters/#1}}{\input{#1}}}
\newcommand\chapterone{\chapter{\chapteronetitle}\cskku@chapterfile{chapter1}}
\newcommand\chaptertwo{\chapter{\chaptertwotitle}\cskku@chapterfile{chapter2}}
\newcommand\chapterthree{\chapter{\chapterthreetitle}\cskku@chapterfile{chapter3}}
\newcommand\chapterfour{\chapter{\chapterfourtitle}\cskku@chapterfile{chapter4}}
\newcommand\chapterfive{\chapter{\chapterfivetitle}\cskku@chapterfile{chapter5}}

% ---------------------------------------------------------------------
% ภาคผนวก — เข้ากันได้กับคำสั่งเดิม \appendiceschapter{ชื่อ}
% ---------------------------------------------------------------------
\newcommand\appendiceschapter[1]{%
  \ifcskku@inappendix\else\appendix\fi
  \if\relax\detokenize{#1}\relax\else\chapter{#1}\fi}

\endinput
