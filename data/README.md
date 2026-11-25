	# Peirce manuscripts: transcriptions

Automatic transcriptions of Charles S. Peirce's papers at Houghton Library
(MS Am 1632), from the project *Peirce Interprets Peirce*, Bibliotheca Hertziana.
They are machine drafts, made with Google Gemini models and checked by
validators. Most pages have not been proofread.

## Example Layout

```
peirce_transcriptions/
  README.md                     this file
  index.csv                     one row per catalogue record
  collection_metadata.json   the full metadata, one record per manuscript
  manuscripts/
    MS-0285_hou02614c00296/     one folder per manuscript
      iiif/seq1.txt             image 1 of the Houghton colour scan
      microfilm/R-6_0551.txt    frame 0551 of microfilm reel R-6
```

Manuscripts are organized in folders. The folder name corresponds to the Robin catalogue number, then the Houghton id (see below):

- `MS-0277`: manuscript 277, padded to four digits so folders sort in order.
- `MS-0690a`: a lettered sub-unit (690a, 337s, ...). It is a separate record and
  gets its own folder.
- `L-0045`: letter L45 (correspondence).
- `MS-none`: a record with no Robin number.

**The record and the folder share the same id.** The part after the underscore
(`hou02614c00296`) is the Houghton id. It is the `houghton_id` column in
`index.csv` and the `id` of the record in `collection_metadata.json`, and
every record there also has a `package_path` pointing to its folder.

**Two sources, side by side.**

- `iiif/` holds transcriptions of Houghton's colour scans. `seq<N>` is the
  image's position in the Houghton IIIF manifest.
- `microfilm/` holds transcriptions of the 1966 microfilm. `<reel>_<frame>` is
  the reel and the frame number on it. Frames are assigned to manuscripts by the
  project's reel index.

A manuscript can have one source, the other, or both. Where it has both, the
two cover the same pages independently and do not line up page for page.

Some special cases:

- An **empty `.txt` file** is a page judged blank.
- An `iiif/hou…_seq1.txt` file (a Houghton id in the file name) is a single page
  that Houghton catalogued separately and that the metadata files under this
  manuscript.
- A few catalogue records are **excerpts**: a leaf or section of a larger
  manuscript that Houghton imaged on its own. The microfilm frames go to the
  whole manuscript. Such a record's `parent_record` column in `index.csv` names
  the folder where those frames are.

## index.csv

One row per catalogue record (2509), including records with no transcription.
Those have an empty `package_path` and no folder.

| column | meaning |
|---|---|
| `robin` | Robin catalogue number |
| `houghton_id` | Houghton id, also the metadata `id` |
| `title` | catalogue title |
| `category` | Robin category |
| `catalogue_dates` | date(s) given by the Houghton catalogue |
| `iiif_pages`, `microfilm_pages` | number of `.txt` files in this package for each source |
| `package_path` | the manuscript's folder, empty if none |
| `houghton_manifest` | Houghton's IIIF manifest |
| `hertziana_manifest` | the project's IIIF manifest on the Hertziana server, where one exists |
| `parent_record` | for an excerpt record, the folder holding its microfilm frames |

## Markup

The text is plain UTF-8 with square-bracket tags. A tag is opened with
`[tag]` and closed with `[/tag]`.

| tag | meaning |
|---|---|
| `[del]…[/del]` | deleted (struck through) by Peirce |
| `[ins]…[/ins]` | inserted by Peirce (above the line, in the margin, …) |
| `[u]…[/u]` | underlined; `[ured]` underlined in red |
| `[sup]`, `[sub]` | superscript, subscript |
| `[i]`, `[b]`, `[red]`, `[small]`, `[box]` | italic, bold, red ink, small, boxed |
| `[marginalia]…[/marginalia]` | note in the margin; `[footnote]` a footnote |
| `[pn]…[/pn]` | Peirce's own page number or corner code |
| `[date]…[/date]` | a date Peirce wrote |
| `[fig]…[/fig]` | a figure or diagram, with a short description |
| `[math]…[/math]`, `$…$` | mathematics, in LaTeX |
| `[greek]…[/greek]`, `[foreign]…[/foreign]` | Greek, other foreign words |
| `[unclear]…[/unclear]` | reading uncertain |
| `[illegible]`, `[gap]`, `[space]` | nothing legible; a blank Peirce left; a deliberate space |

You will also find some markup drift: `<u>` written as HTML, a page wrapped in
```` ``` ````, or an invented tag. Treat these as the tags above.
