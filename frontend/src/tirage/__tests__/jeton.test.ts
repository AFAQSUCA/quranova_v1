import { beforeEach, describe, expect, it } from "vitest";

import { chargerJeton, oublierJeton } from "../jeton";

describe("jeton du terminal (D31)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/tirage/");
  });

  it("lit le jeton dans le fragment, le garde et efface l'adresse", () => {
    window.history.replaceState(null, "", "/tirage/#secret-123");

    expect(chargerJeton()).toBe("secret-123");

    expect(window.location.hash).toBe("");
    expect(window.localStorage.getItem("quranova.jeton_tirage")).toBe("secret-123");
  });

  it("retrouve le jeton gardé quand l'adresse n'en contient plus", () => {
    window.localStorage.setItem("quranova.jeton_tirage", "garde");

    expect(chargerJeton()).toBe("garde");
  });

  it("renvoie null sans jeton", () => {
    expect(chargerJeton()).toBeNull();
  });

  it("oublie le jeton", () => {
    window.localStorage.setItem("quranova.jeton_tirage", "x");

    oublierJeton();

    expect(chargerJeton()).toBeNull();
  });
});
