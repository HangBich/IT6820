import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.circuit.CircuitState;
import com.cburch.logisim.comp.ComponentDrawContext;
import com.cburch.logisim.data.Bounds;
import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.proj.Project;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.Collections;
import javax.imageio.ImageIO;

/**
 * Renders circuits of a .circ to PNG files (as Logisim draws them, with the
 * initial simulation state).
 *
 * Usage: java -cp logisim.jar:. Render file.circ outdir scale [circuit...]
 */
public class Render {
  public static void main(String[] args) throws Exception {
    System.setProperty("java.awt.headless", "true");
    com.cburch.logisim.Main.headless = true;
    LogisimFile file = new Loader(null).openLogisimFile(new File(args[0]));
    Project proj = new Project(file);
    double scale = Double.parseDouble(args[2]);
    for (Circuit c : file.getCircuits()) {
      boolean want = args.length <= 3;
      for (int i = 3; i < args.length; i++) want |= args[i].equals(c.getName());
      if (!want) continue;
      Bounds b = c.getBounds();
      int pad = 20;
      int w = (int) ((b.getWidth() + 2 * pad) * scale), h = (int) ((b.getHeight() + 2 * pad) * scale);
      BufferedImage img = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
      Graphics2D g = img.createGraphics();
      g.setColor(Color.WHITE);
      g.fillRect(0, 0, w, h);
      g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
      g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
      g.scale(scale, scale);
      g.translate(pad - b.getX(), pad - b.getY());
      CircuitState state = CircuitState.createRootState(proj, c);
      ComponentDrawContext ctx = new ComponentDrawContext(null, c, state, g.create(), g, true);
      ctx.setShowState(false);
      c.draw(ctx, Collections.emptySet());
      File out = new File(args[1], c.getName() + ".png");
      ImageIO.write(img, "png", out);
      System.out.println(out + " " + w + "x" + h);
    }
    System.exit(0);
  }
}
