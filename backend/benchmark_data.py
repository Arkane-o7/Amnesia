"""Curated, annotated natural-language cases, separate from the local grammar.

Gold values and transition labels are authored here; they are never produced by
the evaluated model. This is an internal review set, not an external benchmark.
"""
from .evaluate import CATEGORIES


def natural_cases():
    cases = []
    cities = [("Hyderabad", "Chennai"), ("Pune", "Kochi"), ("Jaipur", "Bengaluru")]
    languages = [("Python", "Rust"), ("Java", "Kotlin"), ("JavaScript", "TypeScript")]
    pets = [("Bruno", "Milo"), ("Luna", "Nova"), ("Max", "Leo")]
    def fact(relation, value, intent="assert", subject="You", scope=""):
        return {"subject": subject, "relation": relation, "value": value, "intent": intent, "scope": scope}
    def question(text, expected, targets, evolved=False, stale=None, aliases=None):
        return {"text": text, "expected": expected, "targets": targets, "evolved": evolved, "stale": stale or [], "aliases": aliases or []}
    for variant in range(3):
        old, new = cities[variant]
        a, b = languages[variant]
        pet_old, pet_new = pets[variant]
        company = ["Meridian", "Northstar", "Cedar"][variant]
        project = ["Atlas", "Orion", "Aurora"][variant]
        for category in CATEGORIES:
            preserved = []
            if category == "stable":
                turns = ["For your notes, my birthday falls on 14 May. I work for %s." % company, "Just confirming that my birthday is still 14 May."]
                gold = [[fact("birthday", "14 May"), fact("works_at", company)], [fact("birthday", "14 May", "support")]]
                labels = [["UNRELATED", "UNRELATED"], ["SUPPORTS"]]
                questions = [question("When is my birthday?", "14 May", [fact("birthday", "14 May")], aliases=["May 14", "May 14th"]), question("Who is my employer?", company, [fact("works_at", company)])]
                preserved = gold[0]
            elif category == "preference":
                turns = ["My preferred programming language is %s. Coffee is my favourite drink." % a, "I've switched to %s as my preferred programming language. My drink preference hasn't changed." % b]
                gold = [[fact("prefers", a, scope="programming_language"), fact("prefers", "coffee", scope="beverage")], [fact("prefers", b, "update", scope="programming_language"), fact("prefers", "coffee", "support", scope="beverage")]]
                labels = [["UNRELATED", "UNRELATED"], ["SUPERSEDES", "SUPPORTS"]]
                questions = [question("Which programming language do I prefer now?", b, [gold[1][0]], True, [a]), question("What drink do I prefer?", "coffee", [gold[0][1]])]
                preserved = [gold[0][1]]
            elif category == "location":
                turns = ["Home for me is %s. I'm employed by %s." % (old, company), "I've relocated to %s; that's my permanent home now." % new]
                gold = [[fact("lives_in", old), fact("works_at", company)], [fact("lives_in", new, "update")]]
                labels = [["UNRELATED", "UNRELATED"], ["SUPERSEDES"]]
                questions = [question("Which city is my permanent home now?", new, [gold[1][0]], True, [old]), question("Where do I work?", company, [gold[0][1]])]
                preserved = [gold[0][1]]
            elif category == "correction":
                turns = ["Please remember: my meeting is scheduled for Tuesday. I work at %s." % company, "I gave you the wrong meeting day earlier. The correct day is Wednesday."]
                gold = [[fact("meeting_day", "Tuesday"), fact("works_at", company)], [fact("meeting_day", "Wednesday", "correct")]]
                labels = [["UNRELATED", "UNRELATED"], ["UPDATES"]]
                questions = [question("What day is my meeting?", "Wednesday", [gold[1][0]], True, ["Tuesday"]), question("Who is my employer?", company, [gold[0][1]])]
                preserved = [gold[0][1]]
            elif category == "cancellation":
                turns = ["I'm planning a trip to %s. My employer is %s." % (old, company), "I've called off the trip to %s. It isn't happening." % old]
                gold = [[fact("plans_to", old), fact("works_at", company)], [fact("plans_to", old, "cancel")]]
                labels = [["UNRELATED", "UNRELATED"], ["SUPERSEDES"]]
                questions = [question("Do I have an active trip planned?", None, [gold[1][0]], True, [old]), question("Where do I work?", company, [gold[0][1]])]
                preserved = [gold[0][1]]
            elif category == "replacement":
                turns = ["My current phone is an iPhone. I also own a MacBook.", "I've sold the iPhone and replaced it with a Pixel."]
                gold = [[fact("owns", "iPhone"), fact("owns", "MacBook")], [fact("owns", "iPhone", "cancel"), fact("owns", "Pixel")]]
                labels = [["UNRELATED", "UNRELATED"], ["SUPERSEDES", "UNRELATED"]]
                questions = [question("Which phone do I use now?", "Pixel", [gold[1][1]], True, ["iPhone"]), question("Which laptop do I own?", "MacBook", [gold[0][1]])]
                preserved = [gold[0][1]]
            elif category == "temporary":
                turns = ["I make my permanent home in %s." % old, "I'm spending this week in %s, just for a temporary visit." % new]
                gold = [[fact("lives_in", old)], [fact("temporary_location", new)]]
                labels = [["UNRELATED"], ["UNRELATED"]]
                questions = [question("Where is my permanent home?", old, [gold[0][0]]), question("Where am I staying temporarily this week?", new, [gold[1][0]])]
                preserved = gold[0]
            elif category == "additive":
                turns = ["I'm on the payroll at %s." % company, "In addition to my job, I'm heading up Project %s." % project]
                gold = [[fact("works_at", company)], [fact("leads", "Project " + project)]]
                labels = [["UNRELATED"], ["UNRELATED"]]
                questions = [question("Who is my employer?", company, [gold[0][0]]), question("Which project do I lead?", "Project " + project, [gold[1][0]], aliases=[project])]
                preserved = gold[0]
            elif category == "rename":
                turns = ["We call my dog %s. I work at %s." % (pet_old, company), "We've renamed my dog to %s. It's the same dog, just a new name." % pet_new]
                gold = [[fact("name", pet_old, subject="Your dog"), fact("works_at", company)], [fact("name", pet_new, "update", subject="Your dog")]]
                labels = [["UNRELATED", "UNRELATED"], ["SUPERSEDES"]]
                questions = [question("What is my dog's current name?", pet_new, [gold[1][0]], True, [pet_old]), question("Who is my employer?", company, [gold[0][1]])]
                preserved = [gold[0][1]]
            else:
                turns = ["I live in %s. I work for %s." % (old, company), "I'm not certain, but I might be living in %s now. Please don't treat that as confirmed." % new]
                gold = [[fact("lives_in", old), fact("works_at", company)], [fact("lives_in", new, "uncertain")]]
                labels = [["UNRELATED", "UNRELATED"], ["CONTRADICTS"]]
                questions = [question("Where do I live?", "UNRESOLVED", [gold[0][0], gold[1][0]], True), question("Who is my employer?", company, [gold[0][1]])]
                preserved = [gold[0][1]]
            cases.append({"id": "natural-%s-%d" % (category, variant+1), "category": category, "turns": turns, "gold_assertions": gold, "gold_labels": labels, "questions": questions, "preserved": preserved})
    return cases
