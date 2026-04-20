# Repo. Information
It is WebRSSBench,it contain: color robustness,text robustness and layout robustness. Position.py is the code for selecting and generating labels when testing relative positional relationships which input is HTML.

Color Robustness — Adversarial Sample Generation
Script: colorRobustness.py
Given an input HTML file, this script generates perturbed HTML with color-based adversarial modifications. Three perturbation modes are supported:
1.low-contrast  Injects a global stylesheet that reduces foreground–background contrast below WCAG 2.1 AA standards (< 4.5:1 ratio), simulating low-visibility conditions. |
2.recolor  Randomly shifts the chroma of 10%–100% of actionable buttons to random colors (excluding black/white), testing whether the model relies on color cues. |


Text Robustness — Adversarial Sample Generation
Script: TextRobustness.py
Given an input HTML file, this script applies content-preserving but form-disruptive edits to button labels. The perturbations include:
Whitespace injection: Inserting spaces within button text (e.g., "Submit" → "S u b m i t")
Exclamation marks: Appending or inserting exclamation marks
Symbolic perturbations: Replacing characters with common symbols
Visually similar character substitution: Swapping characters with look-alikes (e.g., "o" → "0", "l" → "1")
These edits are constrained to preserve the functional intent of the button at the UI level.

Layout Robustness — Adversarial Sample Generation
Script: layoutRobustness.py
Given an input HTML file, this script applies minimal DOM-level modifications that preserve the page's core functionality and the position of the primary call-to-action (CTA) element. The modifications include:
Node deletion: Removing non-essential DOM nodes
Node insertion: Adding new DOM elements into the page structure
Node relocation: Moving existing DOM nodes to different positions in the tree
These changes simulate routine front-end updates that introduce minor layout variations without altering the overall structural semantics.

Position Relationship Reasoning — Automatic QA Generation
Script: position.py
Given an input HTML file, this script automatically generates position relationship QA pairs by:
Parsing the HTML source and extracting all visible elements with bounding-box coordinates.
Randomly sampling element pairs from the page.
Computing the precise spatial relationship between each pair based on their bounding-box positions.

You can find our datasets in Huggingface link [https./figs//huggingface.c./figs/dataset./figs/annoy-worke./figs/WebRSSBench](https://huggingface.co/datasets/annoy-worker/WebRSSBench)



# Please see appendix below:
![](./figs/appendix_(delete)_01.png)
![](./figs/appendix_(delete)_02.png)
![](./figs/appendix_(delete)_03.png)
![](./figs/appendix_(delete)_04.png)
![](./figs/appendix_(delete)_05.png)
![](./figs/appendix_(delete)_06.png)
![](./figs/appendix_(delete)_07.png)
![](./figs/appendix_(delete)_08.png)
