# Likely label errors in Hi-ToM

134 questions where SecondOrder's answer (derived from the benchmark's stated rules) and Claude Opus 5.5's answer (no graph, chain-of-thought) agree with each other but not with the gold label. The Hi-ToM generator's history contains a commit 'fix permutation bug' (9117f35d) that changed how nested beliefs are written; these questions are concentrated in orders 2-4. We report raw and audited accuracy; nothing is silently dropped.

| idx | order | deception | question | gold | SecondOrder = Opus |
|---|---|---|---|---|---|
| 241 | 2 | False | Where does Emily think Nathan thinks the onion is? | blue_container | blue_treasure_chest |
| 261 | 3 | False | Where does Owen think Emily thinks Nathan thinks the onion is? | blue_container | blue_treasure_chest |
| 281 | 4 | False | Where does Liam think Owen thinks Emily thinks Nathan thinks the onion is? | blue_container | blue_treasure_chest |
| 285 | 4 | False | Where does Logan think Noah thinks Lily thinks Hannah thinks the turnip is? | green_drawer | red_basket |
| 292 | 4 | False | Where does Jackson think Emma thinks Emily thinks William thinks the corn is? | green_bathtub | green_cupboard |
| 296 | 4 | False | Where does Emily think Jack thinks Jackson thinks Emma thinks the eggplant is? | green_box | blue_drawer |
| 342 | 2 | False | Where does Hannah think Noah thinks the eggplant is? | green_bathtub | blue_cupboard |
| 345 | 2 | False | Where does Hannah think Lily thinks the apple is? | green_bathtub | blue_cupboard |
| 346 | 2 | False | Where does Ella think Emma thinks the spinach is? | red_bottle | green_basket |
| 350 | 2 | False | Where does Elizabeth think Ella thinks the orange is? | red_box | red_envelope |
| 360 | 3 | False | Where does Owen think Charlotte thinks Avery thinks the lettuce is? | green_drawer | green_bathtub |
| 361 | 3 | False | Where does Isabella think Hannah thinks Jacob thinks the tomato is? | green_bottle | green_box |
| 362 | 3 | False | Where does Jack think Hannah thinks Noah thinks the eggplant is? | green_envelope | green_bathtub |
| 365 | 3 | False | Where does Jack think Hannah thinks Lily thinks the apple is? | green_bathtub | blue_cupboard |
| 366 | 3 | False | Where does Aiden think Ella thinks Emma thinks the spinach is? | red_bottle | green_basket |
| 372 | 3 | False | Where does Amelia think Nathan thinks Abigail thinks the cabbage is? | red_container | green_envelope |
| 373 | 3 | False | Where does Jack think Avery thinks Abigail thinks the lime is? | blue_pantry | blue_suitcase |
| 375 | 3 | False | Where does Logan think Evelyn thinks William thinks the carrot is? | red_container | blue_container |
| 380 | 4 | False | Where does Isabella think Owen thinks Charlotte thinks Avery thinks the lettuce is? | green_drawer | green_bathtub |
| 381 | 4 | False | Where does Elizabeth think Isabella thinks Hannah thinks Jacob thinks the tomato is? | green_bottle | green_box |
| 382 | 4 | False | Where does Owen think Jack thinks Hannah thinks Noah thinks the eggplant is? | green_envelope | green_bathtub |
| 385 | 4 | False | Where does Aiden think Jack thinks Hannah thinks Lily thinks the apple is? | green_bathtub | blue_cupboard |
| 386 | 4 | False | Where does Benjamin think Aiden thinks Ella thinks Emma thinks the spinach is? | red_bottle | green_basket |
| 392 | 4 | False | Where does Charlotte think Amelia thinks Nathan thinks Abigail thinks the cabbage is? | red_container | green_envelope |
| 393 | 4 | False | Where does Aiden think Jack thinks Avery thinks Abigail thinks the lime is? | green_envelope | blue_suitcase |
| 395 | 4 | False | Where does Alexander think Logan thinks Evelyn thinks William thinks the carrot is? | red_container | blue_container |
| 399 | 4 | False | Where does Evelyn think Emily thinks Jacob thinks Ava thinks the watermelon is? | blue_cupboard | green_bottle |
| 442 | 2 | False | Where does Noah think Benjamin thinks the peas is? | blue_container | green_crate |
| 448 | 2 | False | Where does Owen think Noah thinks the carrot is? | red_pantry | green_drawer |
| 453 | 2 | False | Where does Sophia think Isla thinks the lemon is? | red_box | red_container |
| 454 | 2 | False | Where does Nathan think Abigail thinks the corn is? | red_basket | green_bathtub |
| 455 | 2 | False | Where does Liam think Benjamin thinks the tangerine is? | green_bottle | blue_treasure_chest |
| 456 | 2 | False | Where does Emily think Owen thinks the lime is? | red_bottle | blue_drawer |
| 459 | 2 | False | Where does Emily think Nathan thinks the peas is? | blue_suitcase | red_basket |
| 462 | 3 | False | Where does Liam think Noah thinks Benjamin thinks the peas is? | green_drawer | blue_container |
| 464 | 3 | False | Where does Emma think Aiden thinks Avery thinks the cabbage is? | green_envelope | green_box |
| 465 | 3 | False | Where does Benjamin think Avery thinks Owen thinks the melon is? | red_pantry | green_basket |
| 466 | 3 | False | Where does Isabella think Lily thinks Nathan thinks the melon is? | blue_container | green_treasure_chest |
| 470 | 3 | False | Where does Ella think Lily thinks Avery thinks the cherry is? | red_drawer | red_container |
| 473 | 3 | False | Where does Evelyn think Sophia thinks Isla thinks the lemon is? | red_box | red_container |
| 474 | 3 | False | Where does Avery think Nathan thinks Abigail thinks the corn is? | red_basket | green_bathtub |
| 475 | 3 | False | Where does Carter think Liam thinks Benjamin thinks the tangerine is? | green_bottle | blue_treasure_chest |
| 476 | 3 | False | Where does Lily think Emily thinks Owen thinks the lime is? | red_bottle | blue_drawer |
| 479 | 3 | False | Where does Ella think Emily thinks Nathan thinks the peas is? | blue_suitcase | red_basket |
| 481 | 4 | False | Where does Liam think Sophia thinks Lily thinks Amelia thinks the corn is? | red_basket | red_container |
| 482 | 4 | False | Where does Avery think Liam thinks Noah thinks Benjamin thinks the peas is? | green_drawer | blue_container |
| 484 | 4 | False | Where does Noah think Emma thinks Aiden thinks Avery thinks the cabbage is? | green_envelope | green_box |
| 485 | 4 | False | Where does Noah think Benjamin thinks Avery thinks Owen thinks the melon is? | red_pantry | green_basket |
| 486 | 4 | False | Where does Ava think Isabella thinks Lily thinks Nathan thinks the melon is? | blue_container | green_treasure_chest |
| 488 | 4 | False | Where does Lily think Mila thinks Owen thinks Noah thinks the carrot is? | red_basket | red_pantry |
| 490 | 4 | False | Where does Emily think Ella thinks Lily thinks Avery thinks the cherry is? | red_drawer | red_container |
| 493 | 4 | False | Where does Alexander think Evelyn thinks Sophia thinks Isla thinks the lemon is? | red_box | red_container |
| 494 | 4 | False | Where does Hannah think Avery thinks Nathan thinks Abigail thinks the corn is? | red_basket | green_bathtub |
| 495 | 4 | False | Where does Jackson think Carter thinks Liam thinks Benjamin thinks the tangerine is? | green_bottle | blue_treasure_chest |
| 496 | 4 | False | Where does Ella think Lily thinks Emily thinks Owen thinks the lime is? | red_bottle | blue_drawer |
| 498 | 4 | False | Where does Sophia think Amelia thinks Nathan thinks Jackson thinks the tomato is? | blue_container | blue_cupboard |
| 499 | 4 | False | Where does Evelyn think Ella thinks Emily thinks Nathan thinks the peas is? | blue_suitcase | red_basket |
| 540 | 2 | False | Where does Abigail think Isabella thinks the lettuce is? | blue_treasure_chest | red_basket |
| 543 | 2 | False | Where does Benjamin think Emma thinks the green_pepper is? | red_basket | blue_container |
| 553 | 2 | False | Where does Abigail think Avery thinks the cucumber is? | blue_drawer | blue_container |
| 555 | 2 | False | Where does Hannah think William thinks the persimmon is? | red_basket | blue_crate |
| 558 | 2 | False | Where does William think Noah thinks the pear is? | blue_drawer | green_crate |
| 559 | 2 | False | Where does Jackson think Evelyn thinks the spinach is? | green_drawer | green_cupboard |
| 560 | 3 | False | Where does Nathan think Abigail thinks Isabella thinks the lettuce is? | blue_container | green_cupboard |
| 563 | 3 | False | Where does Jackson think Benjamin thinks Emma thinks the green_pepper is? | red_basket | blue_container |
| 567 | 3 | False | Where does Jack think Nathan thinks Aiden thinks the lemon is? | green_drawer | blue_pantry |
| 573 | 3 | False | Where does Hannah think Abigail thinks Avery thinks the cucumber is? | blue_drawer | blue_container |
| 575 | 3 | False | Where does Avery think Hannah thinks William thinks the persimmon is? | red_basket | blue_crate |
| 577 | 3 | False | Where does Owen think Alexander thinks Elizabeth thinks the lime is? | blue_crate | green_pantry |
| 580 | 4 | False | Where does Logan think Nathan thinks Abigail thinks Isabella thinks the lettuce is? | blue_container | green_cupboard |
| 582 | 4 | False | Where does Mila think Carter thinks Amelia thinks Isla thinks the peas is? | green_treasure_chest | blue_bucket |
| 583 | 4 | False | Where does Abigail think Jackson thinks Benjamin thinks Emma thinks the green_pepper is? | red_basket | blue_container |
| 587 | 4 | False | Where does Liam think Jack thinks Nathan thinks Aiden thinks the lemon is? | green_drawer | blue_pantry |
| 592 | 4 | False | Where does Jackson think Emma thinks Emily thinks William thinks the corn is? | green_bathtub | green_cupboard |
| 593 | 4 | False | Where does Owen think Hannah thinks Abigail thinks Avery thinks the cucumber is? | blue_drawer | blue_container |
| 595 | 4 | False | Where does Alexander think Avery thinks Hannah thinks William thinks the persimmon is? | red_basket | blue_crate |
| 596 | 4 | False | Where does Emily think Jack thinks Jackson thinks Emma thinks the eggplant is? | green_pantry | blue_drawer |
| 597 | 4 | False | Where does Nathan think Owen thinks Alexander thinks Elizabeth thinks the lime is? | blue_crate | green_pantry |
| 742 | 2 | True | Where does Hannah think Emma thinks the peas is? | blue_treasure_chest | red_bottle |
| 762 | 3 | True | Where does Chloe think Hannah thinks Emma thinks the peas is? | blue_treasure_chest | red_bottle |
| 782 | 4 | True | Where does Logan think Chloe thinks Hannah thinks Emma thinks the peas is? | blue_treasure_chest | red_bottle |
| 794 | 4 | True | Where does Nathan think Ava thinks Noah thinks Charlotte thinks the potato is? | blue_cupboard | green_bottle |
| 881 | 4 | True | Where does Evelyn think Ella thinks Owen thinks Aiden thinks the melon is? | blue_treasure_chest | blue_bottle |
| 941 | 2 | True | Where does Avery think Lily thinks the lemon is? | blue_treasure_chest | blue_pantry |
| 947 | 2 | True | Where does Benjamin think Isla thinks the lettuce is? | red_bucket | red_box |
| 950 | 2 | True | Where does Ava think Sophia thinks the pear is? | blue_crate | green_envelope |
| 951 | 2 | True | Where does Logan think Ava thinks the tangerine is? | red_bottle | green_box |
| 952 | 2 | True | Where does Elizabeth think Owen thinks the onion is? | red_crate | green_bucket |
| 957 | 2 | True | Where does Nathan think William thinks the cabbage is? | green_pantry | red_box |
| 967 | 3 | True | Where does Sophia think Benjamin thinks Isla thinks the lettuce is? | red_bucket | red_box |
| 970 | 3 | True | Where does Avery think Ava thinks Sophia thinks the pear is? | blue_crate | green_envelope |
| 976 | 3 | True | Where does Hannah think Evelyn thinks Alexander thinks the green_pepper is? | blue_crate | blue_suitcase |
| 977 | 3 | True | Where does Aiden think Nathan thinks William thinks the cabbage is? | red_bucket | red_box |
| 979 | 3 | True | Where does Benjamin think Liam thinks Avery thinks the peach is? | red_basket | blue_treasure_chest |
| 981 | 4 | True | Where does Noah think Liam thinks Avery thinks Lily thinks the lemon is? | blue_bathtub | blue_treasure_chest |
| 982 | 4 | True | Where does Elizabeth think Emily thinks Avery thinks Lily thinks the onion is? | green_crate | blue_pantry |
| 985 | 4 | True | Where does Emma think Owen thinks Carter thinks William thinks the watermelon is? | green_crate | green_envelope |
| 987 | 4 | True | Where does Emily think Sophia thinks Benjamin thinks Isla thinks the lettuce is? | red_bucket | red_box |
| 990 | 4 | True | Where does Mila think Avery thinks Ava thinks Sophia thinks the pear is? | blue_crate | green_envelope |
| 996 | 4 | True | Where does Abigail think Hannah thinks Evelyn thinks Alexander thinks the green_pepper is? | blue_crate | blue_suitcase |
| 997 | 4 | True | Where does Logan think Aiden thinks Nathan thinks William thinks the cabbage is? | red_bucket | green_pantry |
| 1047 | 2 | True | Where does Charlotte think Isla thinks the lettuce is? | blue_cupboard | blue_bathtub |
| 1051 | 2 | True | Where does Jackson think Avery thinks the spinach is? | green_envelope | blue_container |
| 1053 | 2 | True | Where does Amelia think Nathan thinks the pear is? | blue_pantry | green_bucket |
| 1066 | 3 | True | Where does Avery think Emily thinks Aiden thinks the asparagus is? | green_cupboard | green_treasure_chest |
| 1070 | 3 | True | Where does Elizabeth think Liam thinks Benjamin thinks the grapes is? | blue_pantry | blue_suitcase |
| 1071 | 3 | True | Where does Isabella think Jackson thinks Avery thinks the spinach is? | green_envelope | blue_container |
| 1074 | 3 | True | Where does Ava think Noah thinks Charlotte thinks the potato is? | blue_cupboard | green_bottle |
| 1075 | 3 | True | Where does Evelyn think Charlotte thinks Benjamin thinks the cucumber is? | green_crate | red_container |
| 1076 | 3 | True | Where does Abigail think Ella thinks Owen thinks the cherry is? | red_drawer | green_bucket |
| 1084 | 4 | True | Where does Liam think Isabella thinks Emma thinks Benjamin thinks the watermelon is? | blue_bottle | green_drawer |
| 1086 | 4 | True | Where does Hannah think Avery thinks Emily thinks Aiden thinks the asparagus is? | green_cupboard | green_treasure_chest |
| 1087 | 4 | True | Where does Aiden think Amelia thinks Charlotte thinks Isla thinks the lettuce is? | green_pantry | blue_cupboard |
| 1090 | 4 | True | Where does Alexander think Elizabeth thinks Liam thinks Benjamin thinks the grapes is? | blue_pantry | blue_suitcase |
| 1091 | 4 | True | Where does Nathan think Isabella thinks Jackson thinks Avery thinks the spinach is? | green_envelope | blue_container |
| 1094 | 4 | True | Where does Nathan think Ava thinks Noah thinks Charlotte thinks the potato is? | blue_cupboard | green_bottle |
| 1095 | 4 | True | Where does Isla think Evelyn thinks Charlotte thinks Benjamin thinks the cucumber is? | green_crate | red_container |
| 1096 | 4 | True | Where does Emma think Abigail thinks Ella thinks Owen thinks the cherry is? | red_drawer | green_bucket |
| 1098 | 4 | True | Where does Sophia think Emily thinks Noah thinks Benjamin thinks the carrot is? | green_treasure_chest | blue_suitcase |
| 1142 | 2 | True | Where does Jackson think Jacob thinks the spinach is? | red_drawer | green_crate |
| 1146 | 2 | True | Where does Sophia think Amelia thinks the lime is? | green_bottle | green_envelope |
| 1152 | 2 | True | Where does Abigail think Mila thinks the onion is? | blue_bucket | red_bucket |
| 1162 | 3 | True | Where does Jack think Jackson thinks Jacob thinks the spinach is? | red_container | green_crate |
| 1163 | 3 | True | Where does Lily think Nathan thinks Amelia thinks the corn is? | green_bottle | red_envelope |
| 1165 | 3 | True | Where does Jacob think Isabella thinks Owen thinks the orange is? | green_box | blue_bottle |
| 1167 | 3 | True | Where does Avery think Amelia thinks Chloe thinks the carrot is? | red_pantry | red_bucket |
| 1168 | 3 | True | Where does Elizabeth think Carter thinks Isla thinks the watermelon is? | blue_bottle | red_envelope |
| 1175 | 3 | True | Where does Owen think Noah thinks Aiden thinks the cherry is? | green_envelope | blue_bucket |
| 1181 | 4 | True | Where does Evelyn think Ella thinks Owen thinks Aiden thinks the melon is? | blue_treasure_chest | blue_bottle |
| 1182 | 4 | True | Where does Ella think Jack thinks Jackson thinks Jacob thinks the spinach is? | red_container | green_crate |
| 1183 | 4 | True | Where does Alexander think Lily thinks Nathan thinks Amelia thinks the corn is? | green_bottle | red_envelope |
| 1184 | 4 | True | Where does Hannah think Avery thinks Jackson thinks Sophia thinks the sweet_potato is? | red_box | green_bottle |
| 1187 | 4 | True | Where does Sophia think Avery thinks Amelia thinks Chloe thinks the carrot is? | red_pantry | red_bucket |
| 1195 | 4 | True | Where does Ella think Owen thinks Noah thinks Aiden thinks the cherry is? | green_envelope | blue_bucket |