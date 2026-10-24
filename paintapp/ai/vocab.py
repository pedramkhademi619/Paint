"""Things the sketch recogniser can name (QuickDraw-style doodle categories plus a few popular extras)."""

CATEGORIES = """airplane, alarm clock, ambulance, angel, ant, anvil, apple, arm, asparagus, axe, backpack, banana,
bandage, barn, baseball bat, baseball, basket, basketball, bat, bathtub, beach, bear, beard, bed, bee, belt, bench,
bicycle, binoculars, bird, birthday cake, blackberry, blueberry, book, boomerang, bottlecap, bowtie, bracelet, brain,
bread, bridge, broccoli, broom, bucket, bulldozer, bus, bush, butterfly, cactus, cake, calculator, calendar, camel,
camera, camouflage, campfire, candle, cannon, canoe, car, carrot, castle, cat, ceiling fan, cell phone, cello, chair,
chandelier, church, circle, clarinet, clock, cloud, coffee cup, compass, computer, cookie, cooler, couch, cow, crab,
crayon, crocodile, crown, cruise ship, cup, diamond, dishwasher, diving board, dog, dolphin, donut, door, dragon,
dresser, drill, drums, duck, dumbbell, ear, elbow, elephant, envelope, eraser, eye, eyeglasses, face, fan, feather,
fence, finger, fire hydrant, fireplace, firetruck, fish, flamingo, flashlight, flip flops, floor lamp, flower,
flying saucer, foot, fork, frog, frying pan, garden hose, garden, giraffe, goatee, golf club, grapes, grass, guitar,
hamburger, hammer, hand, harp, hat, headphones, hedgehog, helicopter, helmet, hexagon, hockey puck, hockey stick,
horse, hospital, hot air balloon, hot dog, hot tub, hourglass, house plant, house, hurricane, ice cream, jacket, jail,
kangaroo, key, keyboard, knee, knife, ladder, lantern, laptop, leaf, leg, light bulb, lighter, lighthouse, lightning,
line, lion, lipstick, lobster, lollipop, mailbox, map, marker, matches, megaphone, mermaid, microphone, microwave,
monkey, moon, mosquito, motorbike, mountain, mouse, moustache, mouth, mug, mushroom, nail, necklace, nose, ocean,
octagon, octopus, onion, oven, owl, paint can, paintbrush, palm tree, panda, pants, paper clip, parachute, parrot,
passport, peanut, pear, peas, pencil, penguin, piano, pickup truck, picture frame, pig, pillow, pineapple, pizza,
pliers, police car, pond, pool, popsicle, postcard, potato, power outlet, purse, rabbit, raccoon, radio, rain,
rainbow, rake, remote control, rhinoceros, rifle, river, roller coaster, rollerskates, sailboat, sandwich, saw,
saxophone, school bus, scissors, scorpion, screwdriver, sea turtle, see saw, shark, sheep, shoe, shorts, shovel, sink,
skateboard, skull, skyscraper, sleeping bag, smiley face, snail, snake, snorkel, snowflake, snowman, soccer ball,
sock, speedboat, spider, spoon, spreadsheet, square, squiggle, squirrel, stairs, star, steak, stereo, stethoscope,
stitches, stop sign, stove, strawberry, streetlight, string bean, submarine, suitcase, sun, swan, sweater, swing set,
sword, syringe, t-shirt, table, teapot, teddy bear, telephone, television, tennis racquet, tent, tiger, toaster, toe,
toilet, tooth, toothbrush, toothpaste, tornado, tractor, traffic light, train, tree, triangle, trombone, truck,
trumpet, umbrella, underwear, van, vase, violin, washing machine, watermelon, waterslide, whale, wheel, windmill,
wine bottle, wine glass, wristwatch, yoga pose, zebra, zigzag,
heart, rocket, robot, ghost, balloon, gift box, castle tower, cottage, tulip, rose, sunflower, bunny, puppy, kitten,
dinosaur, unicorn, pirate ship, fruit basket, cupcake, ice cream cone, crescent moon, shooting star, cloud with rain,
fish tank, treehouse, windmill farm, snowy mountain, campfire with logs, spaceship, alien, pumpkin, christmas tree,
bird house, lamp post, bridge over river, race car, tractor on a field""".replace("\n", " ")

LABELS = sorted({c.strip() for c in CATEGORIES.split(",") if c.strip()})

TEMPLATES = (
    "a simple hand-drawn doodle of {}.",
    "a rough black and white sketch of {}.",
    "a child's drawing of {}.",
)


SINGULAR_ENDING_IN_S = {"glass", "grass", "bus", "school bus", "cactus", "octopus", "asparagus", "hurricane", "lens",
                        "christmas tree", "dress", "compass", "canvas", "walrus", "platypus"}
PLURAL_ONLY = {"scissors", "pants", "shorts", "flip flops", "matches", "peas", "grapes", "stitches", "binoculars",
               "eyeglasses", "headphones", "rollerskates", "drums", "stairs", "underwear", "pliers"}


def with_article(label):
    """'cat' -> 'a cat', 'apple' -> 'an apple', 'scissors' -> 'scissors' (for natural prompts)."""
    label = label.strip()
    if label in PLURAL_ONLY:
        return label
    return ("an " if label[:1].lower() in "aeiou" else "a ") + label
