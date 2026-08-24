% ===============================
% cskkuproject.cls
% Thai Project / Report Class (XeLaTeX)
% สาขาวิชาวิทยาการคอมพิวเตอร์
% วิทยาลัยการคอมพิวเตอร์ มหาวิทยาลัยขอนแก่น
% ===============================
% Based on: cpkkuproject.cls (AI Project template)
% Ref: https://github.com/sekz-zz/kkuthesis/blob/master/kkuthesis.cls

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{cskkuproject}[2026/05/08 CS KKU Project Class]

\newcommand{\ThaiAlph}[1]{%
  \ifcase#1\relax ก\or ข\or ค\or ง\or จ\or ฉ\or ช\or ซ\or ฌ\or ญ\or ฎ\or ฏ\or ฐ\or ฑ\or ฒ\or ณ\or ด\or ต\or ถ\or ท\or ธ\or น\or บ\or ป\or ผ\or ฝ\or พ\or ฟ\or ภ\or ม\or ย\or ร\or ล\or ว\or ศ\or ษ\or ส\or ห\or ฬ\or อ\or ฮ\else ?\fi
}


% ------------------------------------------------
% Base class
% ------------------------------------------------
\LoadClass[12pt,oneside]{report}
% ------------------------------------------------
% Paragraph indentation
% ------------------------------------------------
\RequirePackage{indentfirst}

\newlength{\firstindentlength}
\newlength{\secondindentlength}
\newlength{\thirdindentlength}

\setlength{\firstindentlength}{2.5em}
\setlength{\secondindentlength}{3.5em}
\setlength{\thirdindentlength}{4.5em}

\setlength{\parindent}{\firstindentlength}
\setlength{\parskip}{0pt}
% ------------------------------------------------
% Require XeLaTeX
% ------------------------------------------------
\RequirePackage{ifxetex}
\ifxetex\else
  \ClassError{cskkuproject}
    {This class requires XeLaTeX}
    {Please compile using XeLaTeX}
\fi

% ------------------------------------------------
% Page layout — ตามคู่มือ CS
% ขอบบน 1.5", ขอบซ้าย 1.5", ขอบขวา 1", ขอบล่าง 1"
% ------------------------------------------------
\RequirePackage[
  a4paper,
  top=1.5in,
  left=1.5in,
  right=1in,
  bottom=1in,
  headheight=15pt
]{geometry}

% ------------------------------------------------
% หน้าแรกของแต่ละบทไม่แสดงเลขหน้า
% (\chapter ใช้ \thispagestyle{plain} อัตโนมัติ)
% ------------------------------------------------
\makeatletter
\AtBeginDocument{\let\ps@plain\ps@empty}
\makeatother

% ------------------------------------------------
% Packages
% ------------------------------------------------
\RequirePackage{fontspec}
\RequirePackage{setspace}
\RequirePackage{graphicx}
\RequirePackage{array}      % สำหรับ p{} column type — ต้องโหลดก่อน colortbl
\RequirePackage{booktabs}
\RequirePackage{caption}
\RequirePackage{subcaption}
\RequirePackage{float}
\RequirePackage{fancyhdr}
\RequirePackage{titlesec}
\RequirePackage{microtype}
\RequirePackage{xurl}
\RequirePackage{enumitem}
\RequirePackage{etoolbox}
\RequirePackage{listings}
\lstset{
  basicstyle=\ttfamily\small,
  keywordstyle=\bfseries\color[rgb]{0,0,0.6},
  commentstyle=\itshape\color[rgb]{0,0.5,0},
  stringstyle=\color[rgb]{0.6,0,0},
  numbers=left,
  numberstyle=\tiny\color{gray},
  numbersep=8pt,
  frame=single,
  breaklines=true,
  breakatwhitespace=false,
  tabsize=4,
  showstringspaces=false,
  captionpos=b,
  xleftmargin=1.5em,
  framexleftmargin=1em
}
\RequirePackage{amsmath,amssymb}
% หมายเหตุ: colortbl ไม่โหลดเป็นค่าเริ่มต้นเนื่องจากมีปัญหากับ p{} column
% หากต้องการใช้ \cellcolor ให้เพิ่ม \usepackage{colortbl} ใน main.tex
\RequirePackage{pifont}    % สำหรับ \ding{51} = ✓
\newcommand{\cmark}{\ding{51}}  % ✓ สำหรับตารางเปรียบเทียบ
\RequirePackage{tikz}
\usetikzlibrary{shapes.geometric, arrows.meta, positioning, fit, backgrounds, calc}
\RequirePackage{mermaid}   % Mermaid diagrams — ต้องใช้ -shell-escape และ mmdc CLI



\setlist[itemize]{%
  label=\textbullet
}
\setlist[enumerate]{label*=\arabic*.}

\setlist[itemize,1]{%
  leftmargin=*,
  labelindent=1.5em,
  labelsep=0.7em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.3\baselineskip,
  partopsep=0pt,
}
\setlist[itemize,2]{%
  leftmargin=*,
  labelindent=0.5em,
  labelsep=0.7em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.2\baselineskip,
  partopsep=0pt,
}
\setlist[itemize,3]{%
  leftmargin=*,
  labelindent=0.5em,
  labelsep=0.7em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.2\baselineskip,
  partopsep=0pt,
}

\setlist[enumerate,1]{%
  label=\thesection.\arabic*.,
  leftmargin=*,
  labelwidth=2.5em,
  labelindent=1.5em,
  labelsep=0.7em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.3\baselineskip,
}
\setlist[enumerate,2]{%
  label=\thesection.\arabic{enumi}.\arabic*.,
  leftmargin=*,
  labelwidth=3.0em,
  labelindent=0.5em,
  labelsep=0.7em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.2\baselineskip,
}
\setlist[enumerate,3]{%
  label=\thesection.\arabic{enumi}.\arabic{enumii}.\arabic*.,
  leftmargin=*,
  labelwidth=3.5em,
  labelindent=0.5em,
  labelsep=0.7em,
  listparindent=0pt,
  itemsep=0pt,
  topsep=0.2\baselineskip,
}

\setlist[description]{%
  leftmargin=*,
  labelindent=1.5em,
  labelsep=0.7em,
  listparindent=0pt,
}


\RequirePackage[
  colorlinks=true,
  linkcolor=black,
  urlcolor=blue,
  pageanchor=false
]{hyperref}

\RequirePackage{caption}
% ตาราง: ชื่อชิดซ้าย ตามคู่มือ (ลำดับตารางตัวหนา ชื่อตารางปกติ)
\captionsetup[table]{
  labelfont=bf,
  textfont=normalfont,
  labelsep=space,
  justification=raggedright,
  singlelinecheck=false
}
% ภาพ: ชื่อใต้ภาพ จัดกลาง
\captionsetup[figure]{labelfont=bf,labelsep=space}

% ------------------------------------------------
% คำสั่งสำหรับตาราง/ภาพ ต่อหน้า (ใช้เลขเดิม + "(ต่อ)")
% ------------------------------------------------
% วิธีใช้:
%   \begin{table}[H]
%   \captioncont{ชื่อตาราง}    ← ลำดับเดิม + (ต่อ)
%   \begin{tabular}{...} ... \end{tabular}
%   \end{table}
%
% ใช้ได้ทั้ง table และ figure
% ------------------------------------------------
\newcommand{\captioncont}[1]{%
  \ContinuedFloat
  \caption{#1~(\textnormal{ต่อ})}%
}

% ------------------------------------------------
% ตารางยาวข้ามหน้าอัตโนมัติ (longtable)
% ------------------------------------------------
% ดูตัวอย่างการใช้งานใน guide_format.tex
% ใช้ \endfirsthead, \endhead, \endfoot ของ longtable มาตรฐาน
% ------------------------------------------------
\RequirePackage{longtable}

\makeatletter
\newcommand{\IfEmptyTF}[3]{%
  \edef\@temp{#1}%
  \ifx\@temp\@empty
    #2% true (empty)
  \else
    #3% false (not empty)
  \fi
}
\makeatother
% ------------------------------------------------
% Thai font setup (XeLaTeX)
% ------------------------------------------------
\XeTeXlinebreaklocale "th"
\XeTeXlinebreakskip = 0pt plus 1pt

\pretolerance=1000
\tolerance=2000
\emergencystretch=3em

\setmainfont{Sarabun}[
  Path = ./theme/fonts/,
  Extension = .ttf,
  UprightFont = *-Regular,
  BoldFont = *-Bold,
  ItalicFont = *-Italic,
  BoldItalicFont = *-BoldItalic,
  Scale = 1.4,
]

\setsansfont{Sarabun}[
  Path = ./theme/fonts/,
  Extension = .ttf,
  UprightFont = *-Regular,
  BoldFont = *-Bold,
  ItalicFont = *-Italic,
  BoldItalicFont = *-BoldItalic,
  Scale = 1.4,
]

\setmonofont{DroidSansMono}[
  Path = ./theme/fonts/,
  Extension = .ttf,
  UprightFont = *,
  BoldFont = *,
  ItalicFont = *,
  BoldItalicFont = *,
  Scale = 1.0,
]

% ------------------------------------------------
% Equation, Table, Figure Numbering
% ------------------------------------------------
\makeatletter
\@removefromreset{equation}{chapter}
\@removefromreset{figure}{chapter}
\@removefromreset{table}{chapter}
\makeatother

\renewcommand{\theequation}{\arabic{equation}}
\renewcommand{\thefigure}{\arabic{figure}}
\renewcommand{\thetable}{\arabic{table}}

% ------------------------------------------------
% Line spacing — ตามคู่มือ CS: Single (1.0)
% ------------------------------------------------
\singlespacing

% ------------------------------------------------
% Header / Footer
% ------------------------------------------------
\pagestyle{fancy}
\fancyhf{}
\fancyhead[R]{\thepage}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\makeatletter
\let\ps@plain\ps@fancy
\makeatother

% ------------------------------------------------
% Thai names
% ------------------------------------------------
\renewcommand{\contentsname}{สารบัญ}
\renewcommand{\listtablename}{สารบัญตาราง}
\renewcommand{\listfigurename}{สารบัญภาพ}
\renewcommand{\figurename}{ภาพที่}
\renewcommand{\tablename}{ตารางที่}

% ------------------------------------------------
% Centered TOC / LOT / LOF titles (robust)
% ------------------------------------------------
\makeatletter

\renewcommand{\tableofcontents}{
  \chapter*{\centering\Large\bfseries สารบัญ}
  \addcontentsline{toc}{chapter}{สารบัญ}
  \@starttoc{toc}
}


\renewcommand{\listoftables}{
  \chapter*{\centering\Large\bfseries สารบัญตาราง}
  \addcontentsline{toc}{chapter}{สารบัญตาราง}
  \begingroup
    \let\addvspace\@gobble
    \@starttoc{lot}
  \endgroup
}
\renewcommand*\l@table[2]{%
  \@dottedtocline{1}{0em}{1.5em}{ตารางที่~#1}{#2}%
}

\renewcommand{\listoffigures}{
  \chapter*{\centering\Large\bfseries สารบัญภาพ}
  \addcontentsline{toc}{chapter}{สารบัญภาพ}
  \begingroup
    \let\addvspace\@gobble
    \@starttoc{lof}
  \endgroup
}
\renewcommand*\l@figure[2]{%
  \@dottedtocline{1}{0em}{1.5em}{ภาพที่~#1}{#2}%
}

\makeatother


% ------------------------------------------------
% Title Page Variables
% ------------------------------------------------
\makeatletter
\newcommand{\titleTH}[1]{\def\@titleTH{#1}}
\newcommand{\titleEN}[1]{\def\@titleEN{#1}}
\newcommand{\advisorTH}[1]{\def\@advisorTH{#1}}
\newcommand{\advisorEN}[1]{\def\@advisorEN{#1}}
\newcommand{\degreeTH}[1]{\def\@degreeTH{#1}}
\newcommand{\degreeEN}[1]{\def\@degreeEN{#1}}
\newcommand{\majorTH}[1]{\def\@majorTH{#1}}
\newcommand{\majorEN}[1]{\def\@majorEN{#1}}

\newcommand{\academicYearEN}[1]{\def\@academicYearEN{#1}}
\newcommand{\academicYearTH}[1]{\def\@academicYearTH{#1}}

% รหัสวิชาและภาคเรียน
\newcommand{\courseCode}[1]{\def\@courseCode{#1}}
\newcommand{\courseName}[1]{\def\@courseName{#1}}
\newcommand{\semester}[1]{\def\@semester{#1}}

% ข้อมูลนักศึกษาคนที่ 1
\newcommand{\firstStudentID}[1]{\def\@firstStudentID{#1}}
\newcommand{\firstStudentPrefixTH}[1]{\def\@firstStudentPrefixTH{#1}}
\newcommand{\firstStudentNameTH}[1]{\def\@firstStudentNameTH{#1}}
\newcommand{\firstStudentPrefixEN}[1]{\def\@firstStudentPrefixEN{#1}}
\newcommand{\firstStudentNameEN}[1]{\def\@firstStudentNameEN{#1}}

% ข้อมูลนักศึกษาคนที่ 2
\newcommand{\secondStudentID}[1]{\def\@secondStudentID{#1}}
\newcommand{\secondStudentPrefixTH}[1]{\def\@secondStudentPrefixTH{#1}}
\newcommand{\secondStudentNameTH}[1]{\def\@secondStudentNameTH{#1}}
\newcommand{\secondStudentPrefixEN}[1]{\def\@secondStudentPrefixEN{#1}}
\newcommand{\secondStudentNameEN}[1]{\def\@secondStudentNameEN{#1}}

% ค่าเริ่มต้น
\def\@courseCode{CP354 771}
\def\@courseName{โครงงานคอมพิวเตอร์ 1}
\def\@semester{1}
\def\@secondStudentID{}
\def\@secondStudentPrefixTH{}
\def\@secondStudentNameTH{}
\def\@secondStudentPrefixEN{}
\def\@secondStudentNameEN{}

% ------------------------------------------------
% Title Page — ตามรูปแบบคู่มือ CS
% ------------------------------------------------
\newcommand{\maketitlepage}{
\begin{titlepage}
\clearpage
\thispagestyle{empty}
\centering

\includegraphics[scale=0.5]{./theme/kku-logo.png}

{\Large\bfseries CS3-7} \par
\vspace{0.5cm}
{\Large\bfseries รายงานทางความก้าวหน้าโครงงาน ครั้งที่ 1}

\vfill

{\Large \@titleTH \\[0.5cm] \@titleEN}

\vfill

{\large โดย \\}
{\large \@firstStudentID~\@firstStudentPrefixTH\@firstStudentNameTH \\}
\IfEmptyTF{\@secondStudentID}{}{%
  {\large \@secondStudentID~\@secondStudentPrefixTH\@secondStudentNameTH \\}%
}
\vspace{1cm}

{\large อาจารย์ที่ปรึกษา \\ \@advisorTH \\}

\vfill

{\large รายงานฉบับนี้เป็นส่วนหนึ่งของการศึกษา\\}
{\large วิชา \@courseCode{} \@courseName\\}
{\large หลักสูตร\@degreeTH{} สาขาวิชา\@majorTH\\}
{\large วิทยาลัยการคอมพิวเตอร์\\}
{\large มหาวิทยาลัยขอนแก่น\\}
{\large ปีการศึกษา \@academicYearTH}

\end{titlepage}
}

% ------------------------------------------------
% Progress Report Cover Page (optional)
% ------------------------------------------------
\newcommand{\makeprogresscover}[1]{%  #1 = ครั้งที่ (1 or 2)
\begin{titlepage}
\clearpage
\thispagestyle{empty}
\centering

\includegraphics[scale=0.5]{./theme/kku-logo.png}

{\Large\bfseries รายงานความก้าวหน้าโครงงาน ครั้งที่ #1}

\vfill

{\Large \@titleTH \\[0.5cm] \@titleEN}

\vfill

{\large โดย \\}
{\large \@firstStudentID~\@firstStudentPrefixTH\@firstStudentNameTH \\}
\IfEmptyTF{\@secondStudentID}{}{%
  {\large \@secondStudentID~\@secondStudentPrefixTH\@secondStudentNameTH \\}%
}
\vspace{1cm}

{\large อาจารย์ที่ปรึกษา : \@advisorTH \\}

\vfill

{\large รายงานนี้เป็นส่วนหนึ่งของการศึกษาวิชา \@courseCode{} \@courseName\\}
{\large ภาคเรียนที่ \@semester{} ปีการศึกษา \@academicYearTH\\}
{\large สาขาวิชา\@majorTH{} วิทยาลัยการคอมพิวเตอร์\\}
{\large มหาวิทยาลัยขอนแก่น}

\end{titlepage}
}
\makeatother


% ------------------------------------------------
% Front matter environments
% ------------------------------------------------

\makeatletter
\newenvironment{acknowledgement}{
  \chapter*{กิตติกรรมประกาศ}
  \addcontentsline{toc}{chapter}{กิตติกรรมประกาศ}
}{
\begin{flushright}
ผู้จัดทำ
\\
\@firstStudentNameTH
\\
\IfEmptyTF{\@secondStudentID}{}{\@secondStudentNameTH}
\end{flushright}
\clearpage}
\makeatother

\newenvironment{symbolpage}{
  \chapter*{รายการสัญลักษณ์และคำย่อ}
  \addcontentsline{toc}{chapter}{รายการสัญลักษณ์และคำย่อ}
}{\clearpage}

% ------------------------------------------------
% Biography (ประวัติผู้เขียน) — เพิ่มใหม่ตามคู่มือ CS
% ------------------------------------------------
\newenvironment{biography}{
  \chapter*{ประวัติผู้เขียน}
  \addcontentsline{toc}{chapter}{ประวัติผู้เขียน}
}{\clearpage}

% ------------------------------------------------
% Five-Chapter Structure — ตามหลักสูตร CS
% ------------------------------------------------
\newcommand{\chapterone}{\chapter{บทนำ}\input{chapter1}}
\newcommand{\chaptertwo}{\chapter{ทฤษฎีและงานวิจัยที่เกี่ยวข้อง}\input{chapter2}}
\newcommand{\chapterthree}{\chapter{วิธีการดำเนินโครงงาน}\input{chapter3}}
\newcommand{\chapterfour}{\chapter{การวิเคราะห์ ออกแบบและพัฒนาระบบ}\input{chapter4}}
\newcommand{\chapterfive}{\chapter{สรุปผลการดำเนินงาน}\input{chapter5}}

% ------------------------------------------------
% Bibliography (Thai)
% ------------------------------------------------
\renewcommand{\bibname}{เอกสารอ้างอิง}


% ------------------------------------------------
% Appendices
% ------------------------------------------------

\newcommand{\appendiceschapter}[1]{%
  \clearpage
  \thispagestyle{empty}
  \vspace*{\fill}%
  
  \refstepcounter{chapter}%
  
  \begin{center}
    \if\relax\detokenize{#1}\relax
      {\Large\bfseries ภาคผนวก}%
    \else
      {\Large\bfseries ภาคผนวก~\ThaiAlph{\value{chapter}}}%
      \\
      {\Large\bfseries #1}
    \fi
  \end{center}
  
  \vspace{\fill}        
  \clearpage
  
  % TOC
  \if\relax\detokenize{#1}\relax
    \addcontentsline{toc}{chapter}{ภาคผนวก}%
  \else
    \addcontentsline{toc}{chapter}{ภาคผนวก~\ThaiAlph{\value{chapter}}: #1}%
  \fi

  \ifnum\value{chapter}=0
    \appendix
  \fi
}

% ------------------------------------------------
% Chapter title format — ตามคู่มือ CS
% ชื่อบท: 18pt Bold, Centered
% ------------------------------------------------
\titleformat{\chapter}[display]
  {\bfseries\Large\centering}
  {บทที่~\thechapter}
  {1ex}
  {}

\titleformat{name=\chapter,numberless}[block]
  {\bfseries\Large\centering}
  {}
  {0pt}{}

\titlespacing*{\chapter}
  {0pt}
  {0pt}
  {20pt}

\setcounter{secnumdepth}{4}
\renewcommand\thesection{\thechapter.\arabic{section}}
\renewcommand\thesubsection{\thesection.\arabic{subsection}}
% หัวข้อย่อยระดับที่ 3: (1), (2), (3) ตามคู่มือ
\renewcommand\thesubsubsection{(\arabic{subsubsection})}
% หัวข้อย่อยระดับที่ 4: (1.1), (1.2) ตามคู่มือ
\renewcommand\theparagraph{(\arabic{subsubsection}.\arabic{paragraph})}

% หัวข้อใหญ่: 16pt Bold
\titleformat{\section}
  {\bfseries\large\upshape}
  {\thesection}
  {0.45\firstindentlength}
  {}

\titleformat{name=\section,numberless}
  {\bfseries\large\upshape}
  {}
  {0pt}
  {}

% หัวข้อย่อยระดับที่ 1: 14pt
\titleformat{\subsection}
  {\bfseries\large\upshape}
  {\thesubsection}
  {0.45\firstindentlength}
  {}

\titleformat{name=\subsection,numberless}
  {\bfseries\large\upshape}
  {}
  {0pt}
  {}

% หัวข้อย่อยระดับที่ 2: (1) 14pt
\titleformat{\subsubsection}
  {\bfseries\large\upshape}
  {\thesubsubsection}
  {0.45\firstindentlength}
  {}

\titleformat{name=\subsubsection,numberless}
  {\bfseries\large\upshape}
  {}
  {0pt}
  {}

% หัวข้อย่อยระดับที่ 3: (1.1) 14pt
\titleformat{\paragraph}[hang]
  {\normalfont\normalsize\upshape}
  {\theparagraph}
  {0.45\firstindentlength}
  {}

\titleformat{name=\paragraph,numberless}[hang]
  {\normalfont\normalsize\upshape}
  {}
  {0pt}
  {}

\titlespacing{\section}
  {0pt}
  {0.5\baselineskip}
  {0.0\baselineskip}

\titlespacing{\subsection}
  {\firstindentlength}
  {0.5\baselineskip}
  {0.0\baselineskip}

\titlespacing{\subsubsection}
  {\firstindentlength}
  {0.5\baselineskip}
  {0.0\baselineskip}

\titlespacing{\paragraph}
  {\secondindentlength}
  {0.5\baselineskip}
  {0.0\baselineskip}

\pretocmd{\section}{\setlength{\parindent}{\firstindentlength}}{}{}
\pretocmd{\subsection}{\setlength{\parindent}{\firstindentlength}}{}{}
\pretocmd{\subsubsection}{\setlength{\parindent}{\firstindentlength}}{}{}


\makeatletter

\newif\if@appendixmode
\@appendixmodefalse

\pretocmd{\appendix}{%
  \@appendixmodetrue
}{}{}


\pretocmd{\section}{%
  \if@appendixmode\else
    \setlength{\parindent}{\firstindentlength}%
  \fi
}{}{}

\pretocmd{\subsection}{%
  \if@appendixmode\else
    \setlength{\parindent}{\secondindentlength}%
  \fi
}{}{}

\pretocmd{\subsubsection}{%
  \if@appendixmode\else
    \setlength{\parindent}{\thirdindentlength}%
  \fi
}{}{}

\makeatother

% ------------------------------------------------
% Abstract
% ------------------------------------------------

\newcommand{\projectentry}[2]{%
\parindent=0pt
\hangindent=0pt
\hangafter=1
  {\parindent=0pt
   \hangindent=\firstindentlength
   \hangafter=1
   #1\par}
#2\par
}


\makeatletter

\newcommand{\@keywordsTH}{}
\newcommand{\@keywordsEN}{}

\newcommand{\keywordsTH}[1]{%
  \gdef\@keywordsTH{#1}%
}
\newcommand{\keywordsEN}[1]{%
  \gdef\@keywordsEN{#1}%
}
\newcommand{\printkeywordsTH}{%
  \par\bigskip
  \noindent\textbf{คำสำคัญ: } \@keywordsTH
}
\newcommand{\printkeywordsEN}{%
  \par\bigskip
  \noindent\textbf{Keywords: } \@keywordsEN
}

\newenvironment{abstractTH}{%
  \clearpage
  \addcontentsline{toc}{chapter}{บทคัดย่อ}

  \projectentry
  {
  \IfEmptyTF{\@secondStudentID}
      {\@firstStudentNameTH.}
      {\@firstStudentNameTH\ และ \@secondStudentNameTH.}
  \@academicYearTH{}. \textbf{\@titleTH{}.}
   โครงงานคอมพิวเตอร์. ปริญญา\@degreeTH{} สาขาวิชา\@majorTH{}
   วิทยาลัยการคอมพิวเตอร์ มหาวิทยาลัยขอนแก่น.}
  {\textbf{อาจารย์ที่ปรึกษา:} \@advisorTH}

  \vspace{2.5mm}
  \begin{center}\large\textbf{บทคัดย่อ}\end{center}
  \vspace{2.5mm}
  
  \setlength{\parindent}{\firstindentlength}
  \@afterindenttrue
}{\printkeywordsTH\clearpage}

\newenvironment{abstractEN}{%
  \clearpage
  \addcontentsline{toc}{chapter}{ABSTRACT}

  \projectentry
  {
  \IfEmptyTF{\@secondStudentID}
      {\@firstStudentNameEN.}
      {\@firstStudentNameEN\ and \@secondStudentNameEN.}
  \@academicYearEN{}. \textbf{\@titleEN{}.}
   Computer Project, \@degreeEN{}, Program in \@majorEN{},
   College of Computing, Khon Kaen University.}
  {\textbf{Project Advisor:} \@advisorEN}

  \vspace{2.5mm}
  \begin{center}\large\textbf{ABSTRACT}\end{center}
  \vspace{2.5mm}
  
  \setlength{\parindent}{\firstindentlength}
  \@afterindenttrue
}{\printkeywordsEN\clearpage}

\makeatother

% ------------------------------------------------
% End of class
% ------------------------------------------------
